"""
The implementation of YourNewModel for the partially-observed time-series clustering task.

TODO: modify the above description with your model's information.

"""

# Created by Your Name <Your contact email> TODO: modify the author information.
# License: BSD-3-Clause

from typing import Union, Optional

import torch

from .core import _YourNewModel

# TODO: import the base class from the clustering package in PyPOTS.
#  Here I suppose this is a neural-network clustering model.
#  You should make your model inherent BaseClusterer if it is not a NN.
# from ..base import BaseClusterer
from ..base import BaseNNClusterer
from ...optim.adam import Adam
from ...optim.base import Optimizer


# TODO: define your new model's wrapper here.
#  It should be a subclass of a base class defined in PyPOTS task packages (e.g.
#  BaseNNClusterer of PyPOTS clustering task package), and it has to implement all abstract methods of the base class.
#  Note that this class is a wrapper of your new model and will be directly exposed to users.
class YourNewModel(BaseNNClusterer):
    def __init__(
        self,
        # TODO: add your model's hyper-parameters here
        n_clusters: int,
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
            n_clusters=n_clusters,
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
        # set up the hyper-parameters
        # TODO: set up your model's hyper-parameters here

        # set up the model
        self.model = _YourNewModel(
            # pass the arguments to your model
        )
        self._print_model_size()
        self._send_model_to_given_device()

        # set up the optimizer
        self.optimizer = optimizer
        self.optimizer.init_optimizer(self.model.parameters())

    def _assemble_input_for_training(self, data: list) -> dict:
        raise NotImplementedError

    def _assemble_input_for_validating(self, data: list) -> dict:
        raise NotImplementedError

    def _assemble_input_for_testing(self, data: list) -> dict:
        raise NotImplementedError

    def fit(
        self,
        train_set: Union[dict, str],
        val_set: Optional[Union[dict, str]] = None,
        file_type: str = "hdf5",
    ) -> None:
        raise NotImplementedError

    def predict(
        self,
        test_set: Union[dict, str],
        file_type: str = "hdf5",
    ) -> dict:
        raise NotImplementedError
