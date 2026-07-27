"""A fitted logistic-regression late-payment model (rules → logistic).

The second rung above the rules baseline: the same leakage-safe, as-of-issue
features, but with weights *learned* rather than hand-set, standardised and
L2-regularised. It is a deep module — callers hand it :class:`TrainingExample`s
and it owns vectorisation, scaling, and the single-class edge case — so swapping
in LightGBM later changes only what is behind this seam.

Training-time / offline: fit on a rolling-origin train fold, score the test fold
(see :mod:`cashflow_risk.risk.backtest`). On the synthetic generator this ties the
rules baseline — issue-time signal is weak by construction (docs/adr/0002); the
lift is expected once real Companies House distress signals join the features.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from cashflow_risk.risk.dataset import TrainingExample

# Leakage-safe, as-of-issue features. days_overdue_now is omitted: at the issue
# origin it is always 0 (zero variance), so it carries nothing here. The ch_*
# block is the Companies House view — ch_known separates "no signals available"
# (sole trader / unmatched) from "signals present and clean", so absence is
# never mistaken for health.
FEATURE_NAMES = (
    "customer_late_rate",
    "customer_avg_overdue",
    "terms_days",
    "log_prior_count",
    "is_cold_start",
    "log_amount",
    "ch_known",
    "ch_accounts_overdue",
    "ch_confirmation_overdue",
    "ch_has_insolvency",
    "ch_has_charges",
    "ch_status_not_active",
)


def _feature_row(e: TrainingExample) -> list[float]:
    f = e.features
    row = [
        f.customer_late_rate,
        f.customer_avg_overdue,
        float(f.terms_days),
        math.log1p(f.customer_prior_count),
        1.0 if f.is_cold_start else 0.0,
        math.log1p(f.amount),
    ]
    s = e.signals
    if s is None:
        row += [0.0] * 6
    else:
        row += [
            1.0,
            1.0 if s.accounts_overdue else 0.0,
            1.0 if s.confirmation_overdue else 0.0,
            1.0 if s.has_insolvency else 0.0,
            1.0 if s.has_charges else 0.0,
            1.0 if s.status is not None and s.status != "active" else 0.0,
        ]
    return row


def design_matrix(examples: Sequence[TrainingExample]) -> np.ndarray:
    """The shared feature matrix — every fitted model (logistic, GBM) reads the
    same leakage-safe columns, so bake-off differences are model, not features."""
    if not examples:
        return np.empty((0, len(FEATURE_NAMES)))
    return np.array([_feature_row(e) for e in examples], dtype=float)


class LatePaymentModel:
    """Logistic regression over the as-of-issue feature set."""

    def __init__(self, *, c: float = 1.0) -> None:
        self._c = c
        self._pipeline: Pipeline | None = None
        self._constant: float | None = None  # fallback when training is single-class

    def fit(self, examples: Sequence[TrainingExample]) -> LatePaymentModel:
        y = np.array([1 if e.label else 0 for e in examples], dtype=int)
        if y.size == 0:
            raise ValueError("cannot fit on an empty training set")
        # Logistic regression needs both classes; if a fold is all-late or
        # all-on-time, fall back to predicting that base rate.
        if len(np.unique(y)) < 2:
            self._constant = float(y.mean())
            self._pipeline = None
            return self
        pipeline = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=self._c, max_iter=1000, random_state=0),
        )
        pipeline.fit(design_matrix(examples), y)
        self._pipeline = pipeline
        self._constant = None
        return self

    def predict_proba(self, examples: Sequence[TrainingExample]) -> list[float]:
        if self._pipeline is None and self._constant is None:
            raise RuntimeError("model is not fitted")
        if not examples:
            return []
        if self._constant is not None:
            return [self._constant] * len(examples)
        assert self._pipeline is not None
        proba = self._pipeline.predict_proba(design_matrix(examples))[:, 1]
        return [float(p) for p in proba]
