"""

"""

# Created by Wenjie Du <wenjay.du@gmail.com>
# License: BSD-3-Clause


import torch
from torch.nn.modules.loss import _Loss

from ..functional import (
    calc_mae,
    calc_mse,
    calc_rmse,
    calc_mre,
    calc_quantile_crps,
    calc_quantile_crps_sum,
)


class Criterion(_Loss):
    def __init__(
        self,
        lower_better: bool = True,
    ):
        """The base class for all class implementation loss functions and metrics in PyPOTS.

        Parameters
        ----------
        lower_better :
            Whether the lower value of the criterion directs to a better model performance.
            Default as True which is the case for most loss functions (e.g. MSE, Cross Entropy).
            If False, it makes that the higher value leads to a better model performance (e.g. Accuracy).

        """
        super().__init__()
        self.lower_better = lower_better

    def forward(self, prediction, target):
        raise NotImplementedError


class MSE(Criterion):
    def __init__(self):
        super().__init__()

    def forward(self, prediction, target, mask=None):
        value = calc_mse(prediction, target, mask)
        return value


class MAE(Criterion):
    def __init__(self):
        super().__init__()

    def forward(self, prediction, target, mask=None):
        value = calc_mae(prediction, target, mask)
        return value


class RMSE(Criterion):
    def __init__(self):
        super().__init__()

    def forward(self, prediction, target, mask=None):
        value = calc_rmse(prediction, target, mask)
        return value


class MRE(Criterion):
    def __init__(self):
        super().__init__()

    def forward(self, prediction, target, mask=None):
        value = calc_mre(prediction, target, mask)
        return value


class QuantileCRPS(Criterion):
    def __init__(self):
        super().__init__()

    def forward(self, prediction, target, mask=None):
        value = calc_quantile_crps(prediction, target, mask)
        return value


class QuantileCRPS_Sum(Criterion):
    def __init__(self):
        super().__init__()

    def forward(self, prediction, target, mask=None):
        value = calc_quantile_crps_sum(prediction, target, mask)
        return value


class CrossEntropy(Criterion):
    def __init__(self):
        super().__init__()

    def forward(self, prediction, target):
        value = torch.nn.functional.cross_entropy(prediction, target)
        return value


class NLL(Criterion):
    def __init__(self):
        super().__init__()

    def forward(self, prediction, target):
        value = torch.nn.functional.nll_loss(prediction, target)
        return value
