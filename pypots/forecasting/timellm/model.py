"""
The implementation of TimeLLM for the partially-observed time-series forecasting task.

"""

# Created by Wenjie Du <wenjay.du@gmail.com>
# License: BSD-3-Clause

from copy import deepcopy
from typing import Union, Optional

import torch

from .core import _TimeLLM
from ..base import BaseNNForecaster
from ...nn.modules.loss import Criterion, MSE
from ...optim.adam import Adam
from ...optim.base import Optimizer


class TimeLLM(BaseNNForecaster):
    """The PyTorch implementation of the TimeLLM forecasting model :cite:`jin2024timellm`.

    Parameters
    ----------
    n_steps :
        The number of time steps in the time-series data sample.

    n_features :
        The number of features in the time-series data sample.

    n_pred_steps :
        The number of steps in the forecasting time series.

    n_pred_features :
        The number of features in the forecasting time series.

    term :
        The forecasting term, which can be either 'long' or 'short'.

    llm_model_type :
        The type of the LLM model. It can be one of  ["LLaMA", "GPT2", "BERT"].

    n_layers :
        The number of layers in the TimeLLM model.

    patch_size :
        The length of the patch for the TimeLLM model.

    patch_stride :
        The stride for the patching process in the TimeLLM model.

    d_llm :
        The dimension of the LLM model.
        Given llm_model_type, it should be 4096 for LLaMA, 768 for GPT2 and BERT.

    d_model :
        The dimension of the model.

    d_ffn :
        The dimension of the feed-forward network.

    n_heads :
        The number of heads in each layer of TimeLLM.

    dropout :
        The dropout rate for the model.

    domain_prompt_content :
        The prompt content for the domain knowledge.

    batch_size :
        The batch size for training and evaluating the model.

    epochs :
        The number of epochs for training the model.

    patience :
        The patience for the early-stopping mechanism. Given a positive integer, the training process will be
        stopped when the model does not perform better after that number of epochs.
        Leaving it default as None will disable the early-stopping.

    training_loss:
        The customized loss function designed by users for training the model.
        If not given, will use the default loss as claimed in the original paper.

    validation_metric:
        The customized metric function designed by users for validating the model.
        If not given, will use the default MSE metric.

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
        n_pred_steps: int,
        n_pred_features: int,
        term: str,
        llm_model_type: str,
        n_layers: int,
        patch_size: int,
        patch_stride: int,
        d_llm: int,
        d_model: int,
        d_ffn: int,
        n_heads: int,
        dropout: float,
        domain_prompt_content: str,
        batch_size: int = 32,
        epochs: int = 100,
        patience: Optional[int] = None,
        training_loss: Union[Criterion, type] = MSE,
        validation_metric: Union[Criterion, type] = MSE,
        optimizer: Union[Optimizer, type] = Adam,
        num_workers: int = 0,
        device: Optional[Union[str, torch.device, list]] = None,
        saving_path: Optional[str] = None,
        model_saving_strategy: Optional[str] = "best",
        verbose: bool = True,
    ):
        super().__init__(
            training_loss=training_loss,
            validation_metric=validation_metric,
            batch_size=batch_size,
            epochs=epochs,
            patience=patience,
            num_workers=num_workers,
            device=device,
            enable_amp=True,
            saving_path=saving_path,
            model_saving_strategy=model_saving_strategy,
            verbose=verbose,
        )

        self.n_steps = n_steps
        self.n_features = n_features
        self.n_pred_steps = n_pred_steps
        self.n_pred_features = n_pred_features
        self.term = term
        self.n_layers = n_layers
        self.n_heads = n_heads
        self.d_model = d_model
        self.d_ffn = d_ffn
        self.d_llm = d_llm
        self.patch_size = patch_size
        self.patch_stride = patch_stride
        self.llm_model_type = llm_model_type
        self.dropout = dropout
        self.domain_prompt_content = domain_prompt_content

        # set up the model
        self.model = _TimeLLM(
            n_steps=self.n_steps,
            n_features=self.n_features,
            n_pred_steps=self.n_pred_steps,
            n_pred_features=self.n_pred_features,
            term=self.term,
            n_layers=self.n_layers,
            patch_size=self.patch_size,
            patch_stride=self.patch_stride,
            d_model=self.d_model,
            d_ffn=self.d_ffn,
            d_llm=self.d_llm,
            n_heads=self.n_heads,
            llm_model_type=self.llm_model_type,
            dropout=self.dropout,
            domain_prompt_content=self.domain_prompt_content,
            training_loss=self.training_loss,
            validation_metric=self.validation_metric,
        )
        self._print_model_size()
        self._send_model_to_given_device()

        # set up the optimizer
        if isinstance(optimizer, Optimizer):
            self.optimizer = optimizer
        else:
            self.optimizer = optimizer()  # instantiate the optimizer if it is a class
            assert isinstance(self.optimizer, Optimizer)
        self.optimizer.init_optimizer(self.model.parameters())

    def _organize_content_to_save(self):
        from ...version import __version__ as pypots_version

        if isinstance(self.device, list):
            # to save a DataParallel model generically, save the model.module.state_dict()
            model_state_dict = deepcopy(self.model.module.state_dict())
        else:
            model_state_dict = deepcopy(self.model.state_dict())
        model_state_dict = {k: v for k, v in model_state_dict.items() if "llm" not in k}

        all_attrs = dict({})
        all_attrs["model_state_dict"] = model_state_dict
        all_attrs["pypots_version"] = pypots_version
        return all_attrs
