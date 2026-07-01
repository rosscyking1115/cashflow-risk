"""Rolling-origin (walk-forward), group-aware backtest for the risk model (PLAN §7).

The evaluation protocol that gives Gate 3 teeth:

- **Rolling-origin:** expanding-window temporal folds. Every test example is dated
  on or after the whole training fold — the model is only ever judged on the
  future, never on data it could have peeked at.
- **Cold-start slice:** the subset of each test fold whose customer never appears
  in training. This is the group-aware view — how the model generalises to *new*
  customers, where there is no history to lean on.

A scorer is injected as ``fit_and_score(train, test) -> test_scores``, so the same
protocol judges the rules baseline (which ignores ``train``) and any fitted model
on identical folds. Metrics are pooled across folds and also reported per fold.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from cashflow_risk.risk.dataset import TrainingExample
from cashflow_risk.risk.evaluation import RiskEvaluation, evaluate

FitAndScore = Callable[[list[TrainingExample], list[TrainingExample]], Sequence[float]]


@dataclass(frozen=True)
class Fold:
    """One walk-forward split: train strictly precedes test in issue date."""

    train: list[TrainingExample]
    test: list[TrainingExample]

    @property
    def cold_start_test(self) -> list[TrainingExample]:
        """Test examples for customers unseen in training (group-aware slice)."""
        seen = {e.features.customer_id for e in self.train}
        return [e for e in self.test if e.features.customer_id not in seen]


@dataclass(frozen=True)
class BacktestResult:
    """Pooled and per-fold metrics for one scorer over the rolling-origin folds."""

    n_folds: int
    pooled: RiskEvaluation
    per_fold: list[RiskEvaluation]
    cold_start: RiskEvaluation


def rolling_origin_folds(
    examples: Sequence[TrainingExample], *, n_folds: int = 4, min_train_frac: float = 0.4
) -> list[Fold]:
    """Expanding-window temporal folds, ordered by the example's issue date.

    The first ``min_train_frac`` of the timeline seeds the initial training set;
    the remainder is split into ``n_folds`` contiguous test windows, each training
    on everything strictly before it.
    """
    if n_folds < 1:
        raise ValueError("n_folds must be >= 1")
    ordered = sorted(examples, key=lambda e: e.features.as_of)
    n = len(ordered)
    start = int(n * min_train_frac)
    if start < 1 or start >= n:
        return []
    edges = [start + round((n - start) * i / n_folds) for i in range(n_folds + 1)]
    folds: list[Fold] = []
    for i in range(n_folds):
        lo, hi = edges[i], edges[i + 1]
        if hi <= lo:
            continue
        folds.append(Fold(train=ordered[:lo], test=ordered[lo:hi]))
    return folds


def run_backtest(
    folds: Sequence[Fold], fit_and_score: FitAndScore, *, chase_capacity: int | None = None
) -> BacktestResult:
    """Fit-and-score each fold, then pool the predictions for the headline metrics."""
    per_fold: list[RiskEvaluation] = []
    pooled_y: list[int] = []
    pooled_scores: list[float] = []
    cold_y: list[int] = []
    cold_scores: list[float] = []

    for fold in folds:
        scores = list(fit_and_score(fold.train, fold.test))
        if len(scores) != len(fold.test):
            raise ValueError("fit_and_score returned the wrong number of scores")
        y = [1 if e.label else 0 for e in fold.test]
        per_fold.append(evaluate(y, scores))
        pooled_y.extend(y)
        pooled_scores.extend(scores)

        cold_ids = {id(e) for e in fold.cold_start_test}
        for e, s in zip(fold.test, scores, strict=True):
            if id(e) in cold_ids:
                cold_y.append(1 if e.label else 0)
                cold_scores.append(s)

    return BacktestResult(
        n_folds=len(folds),
        pooled=evaluate(pooled_y, pooled_scores, chase_capacity=chase_capacity),
        per_fold=per_fold,
        cold_start=evaluate(cold_y, cold_scores),
    )
