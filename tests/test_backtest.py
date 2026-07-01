"""Rolling-origin, group-aware backtest — temporal integrity and correct slicing."""

from datetime import date, timedelta

import pytest

from cashflow_risk.features.store import InvoiceFeatures
from cashflow_risk.risk.backtest import Fold, rolling_origin_folds, run_backtest
from cashflow_risk.risk.dataset import TrainingExample


def _ex(day: int, *, cust: str, label: bool) -> TrainingExample:
    f = InvoiceFeatures(
        invoice_id=f"I{day}",
        customer_id=cust,
        as_of=date(2026, 1, 1) + timedelta(days=day),
        amount=1000.0,
        terms_days=30,
        days_overdue_now=0,
        customer_prior_count=1,
        customer_late_rate=0.5,
        customer_avg_overdue=10.0,
        is_cold_start=False,
    )
    return TrainingExample(features=f, label=label)


def test_folds_are_temporally_ordered_train_precedes_test() -> None:
    examples = [_ex(d, cust=f"C{d % 5}", label=d % 2 == 0) for d in range(100)]
    folds = rolling_origin_folds(examples, n_folds=4, min_train_frac=0.4)

    assert len(folds) == 4
    for fold in folds:
        assert fold.train and fold.test
        latest_train = max(e.features.as_of for e in fold.train)
        earliest_test = min(e.features.as_of for e in fold.test)
        assert latest_train <= earliest_test  # never trained on the future


def test_expanding_window_train_grows_each_fold() -> None:
    examples = [_ex(d, cust="C", label=d % 2 == 0) for d in range(100)]
    folds = rolling_origin_folds(examples, n_folds=4)
    sizes = [len(f.train) for f in folds]
    assert sizes == sorted(sizes) and sizes[0] < sizes[-1]


def test_cold_start_slice_is_customers_unseen_in_training() -> None:
    train = [_ex(0, cust="C1", label=True), _ex(1, cust="C2", label=False)]
    test = [_ex(2, cust="C1", label=True), _ex(3, cust="C3", label=False)]
    fold = Fold(train=train, test=test)

    cold = fold.cold_start_test
    assert [e.features.customer_id for e in cold] == ["C3"]  # C1 was seen; C3 is new


def test_run_backtest_pools_predictions_and_validates_length() -> None:
    examples = [_ex(d, cust=f"C{d % 6}", label=d % 3 == 0) for d in range(120)]
    folds = rolling_origin_folds(examples, n_folds=4)

    # trivial scorer: predict the training base rate for every test row
    def base_rate(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
        rate = sum(1 for e in train if e.label) / len(train)
        return [rate] * len(test)

    result = run_backtest(folds, base_rate)
    assert result.n_folds == 4
    assert len(result.per_fold) == 4
    assert result.pooled.n == sum(len(f.test) for f in folds)

    def wrong_length(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
        return [0.5]

    with pytest.raises(ValueError):
        run_backtest(folds, wrong_length)
