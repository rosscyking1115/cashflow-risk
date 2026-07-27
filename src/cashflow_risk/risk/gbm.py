"""The gradient-boosted rung of the risk ladder (rules → logistic →
LightGBM *only if it earns its keep*).

Training-time only: ``lightgbm`` lives in the ``train`` dependency group and is
never installed in the SaaS runtime image — this module may be imported only by
training scripts and tests (enforced by the runtime-import guard test). It reads
the *same* :func:`~cashflow_risk.risk.model.design_matrix` as the logistic
model, so a bake-off difference is the model, never the features.

Verdict to date (synthetic bake-off, ``scripts/bakeoff_risk.py``): it does NOT
earn its keep — the generator's issue-time predictability ceiling binds long
before model capacity does, and a few hundred training examples per fold is
GBM-hostile territory anyway. The rung exists so the same bake-off can re-judge
it the day real data arrives.

Hyperparameters are deliberately conservative for small tabular data: shallow
trees, few leaves, strong minimum-child, single thread for determinism.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

from cashflow_risk.risk.dataset import TrainingExample
from cashflow_risk.risk.model import FEATURE_NAMES, design_matrix


def _frame(examples: Sequence[TrainingExample]) -> pd.DataFrame:
    # a named frame keeps LightGBM's feature-name bookkeeping consistent between
    # fit and predict (and makes feature importances readable)
    return pd.DataFrame(design_matrix(examples), columns=list(FEATURE_NAMES))


class GradientBoostedModel:
    """LightGBM over the shared as-of-issue feature set."""

    def __init__(self, **overrides: Any) -> None:
        self._params: dict[str, Any] = {
            "n_estimators": 200,
            "learning_rate": 0.05,
            "num_leaves": 7,
            "max_depth": 3,
            "min_child_samples": 10,
            "random_state": 0,
            "n_jobs": 1,  # single thread -> bit-reproducible
            "verbosity": -1,
            **overrides,
        }
        self._model: LGBMClassifier | None = None
        self._constant: float | None = None  # fallback when training is single-class

    def fit(self, examples: Sequence[TrainingExample]) -> GradientBoostedModel:
        y = np.array([1 if e.label else 0 for e in examples], dtype=int)
        if y.size == 0:
            raise ValueError("cannot fit on an empty training set")
        if len(np.unique(y)) < 2:  # all-late or all-on-time fold
            self._constant = float(y.mean())
            self._model = None
            return self
        model = LGBMClassifier(**self._params)
        model.fit(_frame(examples), y)
        self._model = model
        self._constant = None
        return self

    def predict_proba(self, examples: Sequence[TrainingExample]) -> list[float]:
        if self._model is None and self._constant is None:
            raise RuntimeError("model is not fitted")
        if not examples:
            return []
        if self._constant is not None:
            return [self._constant] * len(examples)
        assert self._model is not None
        proba = self._model.predict_proba(_frame(examples))[:, 1]
        return [float(p) for p in proba]
