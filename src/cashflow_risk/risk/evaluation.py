"""Evaluation metrics for the late-payment risk model.

The right yardsticks for a rare, ranked-action problem — not accuracy:

- **PR-AUC (average precision)** vs the **prevalence** baseline: precision/recall
  trade-off, judged against the base rate a coin-flip would score.
- **Top-decile precision**, tied to a realistic *chase capacity* (~10 invoices a
  week): of the ones we'd actually chase, how many were truly at risk.
- **Calibration** (Brier score + expected calibration error): would a stated
  score be honest as a probability, so that "70%" means 70%? For this project the
  answer is no — the shipped scorer measures mean ECE 0.186 (0.212 with Companies
  House signals) and systematically over-predicts lateness, which is why its
  output is presented as a ranking score. These functions are the measurement,
  not a claim that it passes. See ``docs/model-evaluation.md``.

Kept dependency-light (numpy only) and hand-checked in tests, so the harness is
trustworthy before it judges any model. scikit-learn arrives with the logistic
model; these stay as the shared, framework-free definitions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


def _as_arrays(y_true: Sequence[int], y_score: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    yt = np.asarray(y_true, dtype=float)
    ys = np.asarray(y_score, dtype=float)
    if yt.shape != ys.shape:
        raise ValueError("y_true and y_score must be the same length")
    return yt, ys


def prevalence(y_true: Sequence[int]) -> float:
    """The positive rate — the base rate PR-AUC must beat to mean anything."""
    yt = np.asarray(y_true, dtype=float)
    return float(yt.mean()) if yt.size else 0.0


def average_precision(y_true: Sequence[int], y_score: Sequence[float]) -> float:
    """Area under the precision-recall curve (interpolation-free, sklearn-style).

    Equals the mean of precision@k evaluated at each positive's rank when scores
    are sorted descending — the standard average-precision definition.
    """
    yt, ys = _as_arrays(y_true, y_score)
    n_pos = float(yt.sum())
    if n_pos == 0:
        return 0.0
    order = np.argsort(-ys, kind="stable")
    y_sorted = yt[order]
    cum_tp = np.cumsum(y_sorted)
    ranks = np.arange(1, y_sorted.size + 1)
    precision_at = cum_tp / ranks
    return float((precision_at * y_sorted).sum() / n_pos)


def top_k_precision(y_true: Sequence[int], y_score: Sequence[float], k: int) -> float:
    """Precision within the top ``k`` highest-scored items (the ones we'd chase)."""
    yt, ys = _as_arrays(y_true, y_score)
    if k <= 0 or yt.size == 0:
        return 0.0
    k = min(k, yt.size)
    top = np.argsort(-ys, kind="stable")[:k]
    return float(yt[top].sum() / k)


def brier_score(y_true: Sequence[int], y_score: Sequence[float]) -> float:
    """Mean squared error of the predicted probabilities (lower is better)."""
    yt, ys = _as_arrays(y_true, y_score)
    return float(np.mean((ys - yt) ** 2)) if yt.size else 0.0


def expected_calibration_error(
    y_true: Sequence[int], y_score: Sequence[float], *, n_bins: int = 10
) -> float:
    """Bin predictions by confidence; average |accuracy − confidence| by bin mass."""
    yt, ys = _as_arrays(y_true, y_score)
    if yt.size == 0:
        return 0.0
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # np.digitize with the interior edges; clamp so 1.0 lands in the last bin.
    bin_idx = np.clip(np.digitize(ys, edges[1:-1]), 0, n_bins - 1)
    ece = 0.0
    for b in range(n_bins):
        mask = bin_idx == b
        count = int(mask.sum())
        if count == 0:
            continue
        acc = float(yt[mask].mean())
        conf = float(ys[mask].mean())
        ece += (count / yt.size) * abs(acc - conf)
    return ece


@dataclass(frozen=True)
class RiskEvaluation:
    """A bundle of the metrics a scorer is judged on."""

    n: int
    prevalence: float
    average_precision: float
    top_decile_precision: float
    calibration_error: float
    brier: float


def evaluate(
    y_true: Sequence[int], y_score: Sequence[float], *, chase_capacity: int | None = None
) -> RiskEvaluation:
    """Compute the full metric bundle. ``chase_capacity`` sets the top-k cutoff;
    it defaults to the top decile."""
    n = len(y_true)
    k = chase_capacity if chase_capacity is not None else max(1, round(0.1 * n))
    return RiskEvaluation(
        n=n,
        prevalence=prevalence(y_true),
        average_precision=average_precision(y_true, y_score),
        top_decile_precision=top_k_precision(y_true, y_score, k),
        calibration_error=expected_calibration_error(y_true, y_score),
        brier=brier_score(y_true, y_score),
    )
