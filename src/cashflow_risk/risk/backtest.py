"""Rolling-origin (walk-forward), group-aware backtest for the risk model.

The evaluation protocol:

- **Rolling-origin:** expanding-window temporal folds, ordered by each example's
  prediction origin. Every test example is dated on or after the whole training
  fold, so no fold is scored on a period its training window has already seen.
- **Purge (label-horizon embargo):** a training example's *label* is not resolved
  at its origin — it closes ``horizon_days`` later. Without a purge, a training
  row issued shortly before the test window carries an outcome from inside that
  window, which is information the model could not have had on the day it would
  really have been fitted. ``purge_days`` drops those rows. It is opt-in because
  it is only correct when the caller knows the label horizon, but on this data it
  changes the answer — see ``docs/model-evaluation.md``.
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
from datetime import timedelta

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
    examples: Sequence[TrainingExample],
    *,
    purge_days: int,
    n_folds: int = 4,
    min_train_frac: float = 0.4,
) -> list[Fold]:
    """Expanding-window temporal folds, ordered by the example's issue date.

    The first ``min_train_frac`` of the timeline seeds the initial training set;
    the remainder is split into ``n_folds`` contiguous test windows, each training
    on everything strictly before it.

    ``purge_days`` is **required, with no default**, and should be set to the label
    horizon. Training examples whose label only resolves at or after the test
    window opens are then dropped, so the training set contains nothing whose
    outcome was still unknown on the day the model would really have been fitted.
    Folds left with no training examples are dropped entirely — with a long horizon
    and a short ledger, the earliest folds have no legitimately trainable history,
    and returning fewer folds is the honest result rather than a silently leaky one.

    It is required rather than defaulted because both available defaults are wrong.
    ``0`` silently reintroduces the leak this argument exists to prevent, which is
    the bug this function shipped with. A hard-coded ``120`` would be right only for
    the horizon this project happens to use and would silently under-purge anything
    longer. The horizon is a property of the caller's dataset, so the caller states
    it. Passing ``purge_days=0`` is legal and means "I want the leaky arm", which
    the bake-off does exactly once, to measure what the leak is worth.
    """
    if n_folds < 1:
        raise ValueError("n_folds must be >= 1")
    if purge_days < 0:
        raise ValueError("purge_days must be >= 0")
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
        train, test = ordered[:lo], ordered[lo:hi]
        if purge_days:
            opens = min(e.features.as_of for e in test)
            cutoff = opens - timedelta(days=purge_days)
            train = [e for e in train if e.features.as_of <= cutoff]
            if not train:
                continue
        folds.append(Fold(train=train, test=test))
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
