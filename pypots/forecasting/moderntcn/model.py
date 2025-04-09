"""
The implementation of ModernTCN for the partially-observed time-series forecasting task.

"""

# Created by Wenjie Du <wenjay.du@gmail.com>
# License: BSD-3-Clause

from typing import Union, Optional

import torch

from .core import _ModernTCN
from ..base import BaseNNForecaster
from ...nn.modules.loss import Criterion, MSE
from ...optim.adam import Adam
from ...optim.base import Optimizer


class ModernTCN(BaseNNForecaster):
    """The PyTorch implementation of the ModernTCN model :cite:`luo2024moderntcn`.

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

    patch_size :
        The size of the patch for the patching mechanism.

    patch_stride :
        The stride for the patching mechanism.

    downsampling_ratio :
        The downsampling ratio for the downsampling mechanism.

    ffn_ratio :
        The ratio for the feed-forward neural network in the model.

    num_blocks :
        The number of blocks for the model. It should be a list of integers.

    large_size :
        The size of the large kernel. It should be a list of odd integers.

    small_size :
        The size of the small kernel. It should be a list of odd integers.

    dims :
        The dimensions for the model. It should be a list of integers.

    small_kernel_merged :
        Whether the small kernel is merged.

    backbone_dropout :
        The dropout rate for the backbone of the model.

    head_dropout :
        The dropout rate for the head of the model.

    use_multi_scale :
        Whether to use multi-scale fusing.

    individual :
        Whether to make a linear layer for each variate/channel/feature individually.

    apply_nonstationary_norm :
        Whether to apply non-stationary normalization.

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
        patch_size: int,
        patch_stride: int,
        downsampling_ratio: float,
        ffn_ratio: float,
        num_blocks: list,
        large_size: list,
        small_size: list,
        dims: list,
        small_kernel_merged: bool = False,
        backbone_dropout: float = 0.1,
        head_dropout: float = 0.1,
        use_multi_scale: bool = True,
        individual: bool = False,
        apply_nonstationary_norm: bool = False,
        batch_size: int = 32,
        epochs: int = 100,
        patience: Optional[int] = None,
        training_loss: Union[Criterion, type] = MSE,
        validation_metric: Union[Criterion, type] = MSE,
        optimizer: Optimizer = Adam(),
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
            saving_path=saving_path,
            model_saving_strategy=model_saving_strategy,
            verbose=verbose,
        )

        self.n_steps = n_steps
        self.n_features = n_features
        self.n_pred_steps = n_pred_steps
        self.n_pred_features = n_pred_features

        # set up the model
        self.model = _ModernTCN(
            n_steps=n_steps,
            n_features=n_features,
            n_pred_steps=n_pred_steps,
            patch_size=patch_size,
            patch_stride=patch_stride,
            downsampling_ratio=downsampling_ratio,
            ffn_ratio=ffn_ratio,
            num_blocks=num_blocks,
            large_size=large_size,
            small_size=small_size,
            dims=dims,
            small_kernel_merged=small_kernel_merged,
            backbone_dropout=backbone_dropout,
            head_dropout=head_dropout,
            use_multi_scale=use_multi_scale,
            individual=individual,
            apply_nonstationary_norm=apply_nonstationary_norm,
            training_loss=self.training_loss,
            validation_metric=self.validation_metric,
        )
        self._print_model_size()
        self._send_model_to_given_device()

        # set up the optimizer
        self.optimizer = optimizer
        self.optimizer.init_optimizer(self.model.parameters())
