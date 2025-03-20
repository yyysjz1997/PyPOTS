"""
The implementation of CSDI for the partially-observed time-series imputation task.

"""

# Created by Wenjie Du <wenjay.du@gmail.com>
# License: BSD-3-Clause

import os
from typing import Union, Optional

import numpy as np
import torch
from torch.utils.data import DataLoader

try:
    import nni
except ImportError:
    pass

from .core import _CSDI
from .data import DatasetForCSDI, TestDatasetForCSDI
from ..base import BaseNNImputer
from ...data.checking import key_in_data_set
from ...optim.adam import Adam
from ...optim.base import Optimizer
from ...utils.logging import logger


class CSDI(BaseNNImputer):
    """The PyTorch implementation of the CSDI model :cite:`tashiro2021csdi`.

    Parameters
    ----------
    n_steps :
        The number of time steps in the time-series data sample.

    n_features :
        The number of features in the time-series data sample.

    n_layers :
        The number of layers in the CSDI model.

    n_heads :
        The number of heads in the multi-head attention mechanism.

    n_channels :
        The number of residual channels.

    d_time_embedding :
        The dimension number of the time (temporal) embedding.

    d_feature_embedding :
        The dimension number of the feature embedding.

    d_diffusion_embedding :
        The dimension number of the diffusion embedding.

    is_unconditional :
        Whether the model is unconditional or conditional.

    target_strategy :
        The strategy for selecting the target for the diffusion process. It has to be one of ["mix", "random"].

    n_diffusion_steps :
        The number of the diffusion step T in the original paper.

    schedule:
        The schedule for other noise levels. It has to be one of ["quad", "linear"].

    beta_start:
        The minimum noise level.

    beta_end:
        The maximum noise level.

    batch_size :
        The batch size for training and evaluating the model.

    epochs :
        The number of epochs for training the model.

    patience :
        The patience for the early-stopping mechanism. Given a positive integer, the training process will be
        stopped when the model does not perform better after that number of epochs.
        Leaving it default as None will disable the early-stopping.

    optimizer :
        The optimizer for model training.
        If not given, will use a default Adam optimizer.

    num_workers :
        The number of subprocesses to use for data loading.
        `0` means data loading will be in the main process, i.e. there won't be subprocesses.

    device :
        The device for the model to run on. It can be a string, a :class:`torch.device` object, or a list of them.
        If not given, will try to use CUDA devices first (will use the default CUDA device if there are multiple),
        then CPUs, considering CUDA and CPU are so far the main devices for people to train ML models.
        If given a list of devices, e.g. ['cuda:0', 'cuda:1'], or [torch.device('cuda:0'), torch.device('cuda:1')] , the
        model will be parallely trained on the multiple devices (so far only support parallel training on CUDA devices).
        Other devices like Google TPU and Apple Silicon accelerator MPS may be added in the future.

    saving_path :
        The path for automatically saving model checkpoints and tensorboard files (i.e. loss values recorded during
        training into a tensorboard file). Will not save if not given.

    model_saving_strategy :
        The strategy to save model checkpoints. It has to be one of [None, "best", "better", "all"].
        No model will be saved when it is set as None.
        The "best" strategy will only automatically save the best model after the training finished.
        The "better" strategy will automatically save the model during training whenever the model performs
        better than in previous epochs.
        The "all" strategy will save every model after each epoch training.

    verbose :
        Whether to print out the training logs during the training process.
    """

    def __init__(
        self,
        n_steps: int,
        n_features: int,
        n_layers: int,
        n_heads: int,
        n_channels: int,
        d_time_embedding: int,
        d_feature_embedding: int,
        d_diffusion_embedding: int,
        n_diffusion_steps: int = 50,
        target_strategy: str = "random",
        is_unconditional: bool = False,
        schedule: str = "quad",
        beta_start: float = 0.0001,
        beta_end: float = 0.5,
        batch_size: int = 32,
        epochs: int = 100,
        patience: Optional[int] = None,
        optimizer: Optimizer = Adam(),
        num_workers: int = 0,
        device: Optional[Union[str, torch.device, list]] = None,
        saving_path: Optional[str] = None,
        model_saving_strategy: Optional[str] = "best",
        verbose: bool = True,
    ):
        super().__init__(
            batch_size=batch_size,
            epochs=epochs,
            patience=patience,
            training_loss=None,
            validation_metric=None,
            num_workers=num_workers,
            device=device,
            saving_path=saving_path,
            model_saving_strategy=model_saving_strategy,
            verbose=verbose,
        )
        assert target_strategy in ["mix", "random"]
        assert schedule in ["quad", "linear"]
        self.n_steps = n_steps
        self.target_strategy = target_strategy

        # CSDI has its own defined loss function and validation loss, so we set them as None here
        self.training_loss = None
        self.training_loss_name = "default"
        self.validation_metric = None
        self.validation_metric_name = "metric (default)"

        # set up the model
        self.model = _CSDI(
            n_features,
            n_layers,
            n_heads,
            n_channels,
            d_time_embedding,
            d_feature_embedding,
            d_diffusion_embedding,
            is_unconditional,
            n_diffusion_steps,
            schedule,
            beta_start,
            beta_end,
        )
        self._print_model_size()
        self._send_model_to_given_device()

        # set up the optimizer
        self.optimizer = optimizer
        self.optimizer.init_optimizer(self.model.parameters())

    def _assemble_input_for_training(self, data: list) -> dict:
        (
            indices,
            X_ori,
            indicating_mask,
            cond_mask,
            observed_tp,
        ) = self._send_data_to_given_device(data)

        inputs = {
            "X_ori": X_ori.permute(0, 2, 1),  # ori observed part for model hint
            "indicating_mask": indicating_mask.permute(0, 2, 1),  # for loss calc
            "cond_mask": cond_mask.permute(0, 2, 1),  # for masking X_ori
            "observed_tp": observed_tp,
        }
        return inputs

    def _assemble_input_for_validating(self, data: list) -> dict:
        return self._assemble_input_for_training(data)

    def _assemble_input_for_testing(self, data: list) -> dict:
        (
            indices,
            X,
            cond_mask,
            observed_tp,
        ) = self._send_data_to_given_device(data)

        inputs = {
            "X": X.permute(0, 2, 1),  # for model input
            "cond_mask": cond_mask.permute(0, 2, 1),  # missing mask
            "observed_tp": observed_tp,
        }
        return inputs

    def _train_model(
        self,
        training_loader: DataLoader,
        val_loader: DataLoader = None,
    ) -> None:
        # each training starts from the very beginning, so reset the loss and model dict here
        self.best_loss = float("inf")
        self.best_model_dict = None

        try:
            training_step = 0
            for epoch in range(1, self.epochs + 1):
                self.model.train()
                epoch_train_loss_collector = []
                for idx, data in enumerate(training_loader):
                    training_step += 1
                    inputs = self._assemble_input_for_training(data)
                    self.optimizer.zero_grad()
                    results = self.model.forward(inputs)
                    # use sum() before backward() in case of multi-gpu training
                    results["loss"].sum().backward()
                    self.optimizer.step()
                    epoch_train_loss_collector.append(results["loss"].sum().item())

                    # save training loss logs into the tensorboard file for every step if in need
                    if self.summary_writer is not None:
                        self._save_log_into_tb_file(training_step, "training", results)

                # mean training loss of the current epoch
                mean_train_loss = np.mean(epoch_train_loss_collector)

                if val_loader is not None:
                    self.model.eval()
                    val_loss_collector = []
                    with torch.no_grad():
                        for idx, data in enumerate(val_loader):
                            inputs = self._assemble_input_for_validating(data)
                            results = self.model.forward(inputs, n_sampling_times=0)
                            val_loss_collector.append(results["loss"].sum().item())

                    mean_val_loss = np.asarray(val_loss_collector).mean()

                    # save validation loss logs into the tensorboard file for every epoch if in need
                    if self.summary_writer is not None:
                        val_loss_dict = {
                            "validating_loss": mean_val_loss,
                        }
                        self._save_log_into_tb_file(epoch, "validating", val_loss_dict)

                    logger.info(
                        f"Epoch {epoch:03d} - "
                        f"training loss ({self.training_loss_name}): {mean_train_loss:.4f}, "
                        f"validation {self.validation_metric_name}: {mean_val_loss:.4f}"
                    )
                    mean_loss = mean_val_loss
                else:
                    logger.info(f"Epoch {epoch:03d} - training loss ({self.training_loss_name}): {mean_train_loss:.4f}")
                    mean_loss = mean_train_loss

                if np.isnan(mean_loss):
                    logger.warning(f"‼️ Attention: got NaN loss in Epoch {epoch}. This may lead to unexpected errors.")

                if (self.validation_metric.lower_better and mean_loss < self.best_loss) or (
                    not self.validation_metric.lower_better and mean_loss > self.best_loss
                ):
                    self.best_epoch = epoch
                    self.best_loss = mean_loss
                    self.best_model_dict = self.model.state_dict()
                    self.patience = self.original_patience
                else:
                    self.patience -= 1

                # save the model if necessary
                self._auto_save_model_if_necessary(
                    confirm_saving=self.best_epoch == epoch and self.model_saving_strategy == "better",
                    saving_name=f"{self.__class__.__name__}_epoch{epoch}_{self.validation_metric_name}{mean_loss:.4f}",
                )

                if os.getenv("ENABLE_HPO", False):
                    nni.report_intermediate_result(mean_loss)
                    if epoch == self.epochs - 1 or self.patience == 0:
                        nni.report_final_result(self.best_loss)

                if self.patience == 0:
                    logger.info("Exceeded the training patience. Terminating the training procedure...")
                    break

        except KeyboardInterrupt:  # if keyboard interrupt, only warning
            logger.warning("‼️ Training got interrupted by the user. Exist now ...")
        except Exception as e:  # other kind of exception follows below processing
            logger.error(f"❌ Exception: {e}")
            if self.best_model_dict is None:  # if no best model, raise error
                raise RuntimeError(
                    "Training got interrupted. Model was not trained. Please investigate the error printed above."
                )
            else:
                RuntimeWarning(
                    "Training got interrupted. Please investigate the error printed above.\n"
                    "Model got trained and will load the best checkpoint so far for testing.\n"
                    "If you don't want it, please try fit() again."
                )

        if np.isnan(self.best_loss) or self.best_loss.__eq__(float("inf")):
            raise ValueError("Something is wrong. best_loss is Nan/Inf after training.")

        logger.info(f"Finished training. The best model is from epoch#{self.best_epoch}.")

    def fit(
        self,
        train_set: Union[dict, str],
        val_set: Optional[Union[dict, str]] = None,
        file_type: str = "hdf5",
        n_sampling_times: int = 1,
    ) -> None:
        # Step 1: wrap the input data with classes Dataset and DataLoader
        training_set = DatasetForCSDI(
            train_set,
            self.target_strategy,
            return_X_ori=False,
            file_type=file_type,
        )
        training_loader = DataLoader(
            training_set,
            batch_size=self.batch_size,
            shuffle=True,
            num_workers=self.num_workers,
        )
        val_loader = None
        if val_set is not None:
            if not key_in_data_set("X_ori", val_set):
                raise ValueError("val_set must contain 'X_ori' for model validation.")
            val_set = DatasetForCSDI(
                val_set,
                self.target_strategy,
                return_X_ori=True,
                file_type=file_type,
            )
            val_loader = DataLoader(
                val_set,
                batch_size=self.batch_size,
                shuffle=False,
                num_workers=self.num_workers,
            )

        # Step 2: train the model and freeze it
        self._train_model(training_loader, val_loader)
        self.model.load_state_dict(self.best_model_dict)

        # Step 3: save the model if necessary
        self._auto_save_model_if_necessary(confirm_saving=self.model_saving_strategy == "best")

    @torch.no_grad()
    def predict(
        self,
        test_set: Union[dict, str],
        file_type: str = "hdf5",
        n_sampling_times: int = 1,
    ) -> dict:
        """Make predictions for the input data with the trained model.

        Parameters
        ----------
        test_set :
            The test dataset for model to process, should be a dictionary including keys as 'X',
            or a path string locating a data file supported by PyPOTS (e.g. h5 file).
            If it is a dict, X should be array-like with shape [n_samples, n_steps, n_features],
            which is the time-series data for processing.
            If it is a path string, the path should point to a data file, e.g. a h5 file, which contains
            key-value pairs like a dict, and it has to include 'X' key.

        file_type :
            The type of the given file if test_set is a path string.

        n_sampling_times:
            The number of sampling times for the model to sample from the diffusion process.

        Returns
        -------
        result_dict: dict
            Prediction results in a Python Dictionary for the given samples.
            It should be a dictionary including a key named 'imputation'.

        """
        assert n_sampling_times > 0, "n_sampling_times should be greater than 0."

        self.model.eval()  # set the model to evaluation mode

        # Step 1: wrap the input data with classes Dataset and DataLoader
        test_set = TestDatasetForCSDI(test_set, return_X_ori=False, file_type=file_type)
        test_loader = DataLoader(
            test_set,
            batch_size=self.batch_size,
            shuffle=False,
            num_workers=self.num_workers,
        )
        imputation_collector = []

        # Step 2: process the data with the model
        for idx, data in enumerate(test_loader):
            inputs = self._assemble_input_for_testing(data)
            results = self.model(
                inputs,
                n_sampling_times=n_sampling_times,
            )
            imputed_data = results["imputed_data"]
            imputation_collector.append(imputed_data)

        # Step 3: output collection and return
        imputation = torch.cat(imputation_collector).cpu().detach().numpy()
        result_dict = {
            "imputation": imputation,
        }
        return result_dict

    def impute(
        self,
        test_set: Union[dict, str],
        file_type: str = "hdf5",
        n_sampling_times: int = 1,
    ) -> np.ndarray:
        """Impute missing values in the given data with the trained model.

        Parameters
        ----------
        test_set :
            The data samples for testing, should be array-like with shape [n_samples, n_steps, n_features], or a path
            string locating a data file, e.g. h5 file.

        file_type :
            The type of the given file if X is a path string.

        n_sampling_times :
            The number of sampling times for the model to sample from the diffusion process.

        Returns
        -------
        array-like, with shape [n_samples, n_sampling_times, n_steps, n_features],
            Imputed data.
        """
        result_dict = self.predict(test_set, file_type, n_sampling_times)
        return result_dict["imputation"]
