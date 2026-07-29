"""Rolling-origin, group-aware backtest — temporal integrity and correct slicing."""

from datetime import date, timedelta

import pytest

from cashflow_risk.datagen.generator import GeneratorConfig, generate_dataset
from cashflow_risk.features.store import InvoiceFeatures
from cashflow_risk.risk.backtest import Fold, rolling_origin_folds, run_backtest
from cashflow_risk.risk.baseline import score_late_probability
from cashflow_risk.risk.dataset import TrainingExample, build_training_examples

HORIZON = 120  # the project's label horizon; the purge must match it


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
    folds = rolling_origin_folds(examples, purge_days=0, n_folds=4, min_train_frac=0.4)

    assert len(folds) == 4
    for fold in folds:
        assert fold.train and fold.test
        latest_train = max(e.features.as_of for e in fold.train)
        earliest_test = min(e.features.as_of for e in fold.test)
        # Origins only. This says nothing about when the labels resolve — see the
        # purge tests below for that.
        assert latest_train <= earliest_test


def test_expanding_window_train_grows_each_fold() -> None:
    examples = [_ex(d, cust="C", label=d % 2 == 0) for d in range(100)]
    folds = rolling_origin_folds(examples, purge_days=0, n_folds=4)
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
    folds = rolling_origin_folds(examples, purge_days=0, n_folds=4)

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


def test_unpurged_folds_train_on_labels_that_close_inside_the_test_window() -> None:
    """The defect the purge exists to fix, pinned so it cannot come back silently."""
    examples = [_ex(d, cust=f"C{d % 5}", label=d % 2 == 0) for d in range(100)]
    folds = rolling_origin_folds(examples, purge_days=0, n_folds=4, min_train_frac=0.4)

    horizon = 30
    leaky = 0
    for fold in folds:
        opens = min(e.features.as_of for e in fold.test)
        leaky += sum(
            1 for e in fold.train if e.features.as_of + timedelta(days=horizon) > opens
        )
    assert leaky > 0  # unpurged: training labels resolve inside the test window


def test_purge_removes_training_rows_whose_label_closes_after_the_test_opens() -> None:
    examples = [_ex(d, cust=f"C{d % 5}", label=d % 2 == 0) for d in range(100)]
    horizon = 30
    folds = rolling_origin_folds(
        examples, purge_days=horizon, n_folds=4, min_train_frac=0.4
    )

    assert folds
    for fold in folds:
        opens = min(e.features.as_of for e in fold.test)
        for e in fold.train:
            assert e.features.as_of + timedelta(days=horizon) <= opens


def test_purge_shrinks_the_training_sets_it_keeps() -> None:
    examples = [_ex(d, cust=f"C{d % 5}", label=d % 2 == 0) for d in range(100)]
    plain = rolling_origin_folds(examples, purge_days=0, n_folds=4, min_train_frac=0.4)
    purged = rolling_origin_folds(examples, purge_days=30, n_folds=4, min_train_frac=0.4)

    assert sum(len(f.train) for f in purged) < sum(len(f.train) for f in plain)


def test_purge_drops_folds_with_no_trainable_history() -> None:
    """A horizon longer than the ledger leaves nothing legitimately trainable."""
    examples = [_ex(d, cust=f"C{d % 5}", label=d % 2 == 0) for d in range(100)]
    assert rolling_origin_folds(examples, purge_days=500, n_folds=4) == []


def test_purge_rejects_a_negative_horizon() -> None:
    examples = [_ex(d, cust="C", label=True) for d in range(100)]
    with pytest.raises(ValueError):
        rolling_origin_folds(examples, purge_days=-1)


def test_purge_days_is_required_and_cannot_be_forgotten() -> None:
    """The leak returned silently once because ``purge_days`` defaulted to 0.

    There is no safe default: 0 restores the bug, and a hard-coded horizon is
    wrong for any dataset that does not share it. So the caller must say.
    """
    examples = [_ex(d, cust="C", label=True) for d in range(100)]
    with pytest.raises(TypeError):
        rolling_origin_folds(examples)  # type: ignore[call-arg]


# --- the invariant guard, on real generated data -----------------------------


def _generated_examples(seed: int = 7, horizon: int = HORIZON) -> list[TrainingExample]:
    cfg = GeneratorConfig(seed=seed, n_customers=30, weeks=52)
    ds = generate_dataset(cfg)
    return build_training_examples(
        ds.invoices,
        horizon_days=horizon,
        observed_until=cfg.start + timedelta(days=cfg.weeks * 7),
    )


def test_no_purged_fold_trains_on_a_label_resolving_inside_its_test_window() -> None:
    """The guard. Fails if the defect returns, on the real generator, not fixtures.

    This is the assertion the harness lacked. It is not about fold ordering: it
    asks, for every training row of every fold, whether the label was already
    resolved on the day the test window opened. If any row's horizon closes at or
    after that day, the model is being fitted on an outcome nobody had yet.
    """
    folds = rolling_origin_folds(_generated_examples(), purge_days=HORIZON, n_folds=4)
    assert folds, "purging must not empty the whole backtest on the default config"

    offenders = []
    for i, fold in enumerate(folds):
        opens = min(e.features.as_of for e in fold.test)
        offenders += [
            (i, e.features.invoice_id, e.features.as_of)
            for e in fold.train
            if e.features.as_of + timedelta(days=HORIZON) > opens
        ]
    assert offenders == [], f"{len(offenders)} training rows leak their label: {offenders[:3]}"


def test_the_unpurged_arm_still_leaks_so_the_guard_is_not_vacuous() -> None:
    """If this ever passes, the guard above proves nothing and both are broken."""
    folds = rolling_origin_folds(_generated_examples(), purge_days=0, n_folds=4)

    leaky = 0
    for fold in folds:
        opens = min(e.features.as_of for e in fold.test)
        leaky += sum(
            1 for e in fold.train if e.features.as_of + timedelta(days=HORIZON) > opens
        )
    assert leaky > 0


def test_purging_cannot_move_the_rules_scorer_the_harness_control() -> None:
    """The control that makes every other purge delta readable.

    The rules scorer ignores its training set entirely — it reads each test row's
    features and nothing else. So changing what is in ``train`` must not change a
    single one of its scores. If purging ever moves this number off zero, the
    comparison between the purged and unpurged arms is measuring fold reshuffling
    rather than the leak, and no delta reported from it can be trusted.
    """
    examples = _generated_examples()
    purged = rolling_origin_folds(examples, purge_days=HORIZON, n_folds=4)
    # match the unpurged arm to the surviving windows, exactly as the bake-off does
    windows = {id(f.test[0]) for f in purged}
    unpurged = [
        f
        for f in rolling_origin_folds(examples, purge_days=0, n_folds=4)
        if f.test and id(f.test[0]) in windows
    ]
    assert len(purged) == len(unpurged) and purged

    def rules(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
        return [score_late_probability(e.features, e.signals).probability for e in test]

    a = run_backtest(purged, rules).pooled
    b = run_backtest(unpurged, rules).pooled

    assert a.n == b.n
    assert a.prevalence == b.prevalence
    lift_a = a.average_precision - a.prevalence
    lift_b = b.average_precision - b.prevalence
    assert lift_a == pytest.approx(lift_b, abs=1e-12), (
        f"purging moved the training-independent control by {lift_a - lift_b:+.6f}; "
        "the two arms are not comparable and the measured leak is not attributable"
    )


def test_a_training_dependent_scorer_does_move_so_the_control_can_discriminate() -> None:
    """The control only means something if the same setup can detect a change."""
    examples = _generated_examples()
    purged = rolling_origin_folds(examples, purge_days=HORIZON, n_folds=4)
    windows = {id(f.test[0]) for f in purged}
    unpurged = [
        f
        for f in rolling_origin_folds(examples, purge_days=0, n_folds=4)
        if f.test and id(f.test[0]) in windows
    ]

    def base_rate(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
        rate = sum(1 for e in train if e.label) / len(train)
        return [rate] * len(test)

    a = run_backtest(purged, base_rate).pooled.brier
    b = run_backtest(unpurged, base_rate).pooled.brier
    assert a != b, "a scorer that reads `train` must respond to purging"
