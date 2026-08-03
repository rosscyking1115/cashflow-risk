"""The fitted logistic late-payment model — mechanics and its ability to learn a
signal when one is present (guarding against a broken pipeline, not asserting a
win on the near-unpredictable synthetic issue-time data)."""

from datetime import date

import pytest

from cashflow_risk.datagen.generator import synthetic_company_number
from cashflow_risk.features.store import InvoiceFeatures
from cashflow_risk.risk.dataset import TrainingExample
from cashflow_risk.risk.evaluation import average_precision, prevalence
from cashflow_risk.risk.model import FEATURE_NAMES, LatePaymentModel


def _ex(
    *, late_rate: float, label: bool, cust: str = "C", amount: float = 1000.0
) -> TrainingExample:
    f = InvoiceFeatures(
        invoice_id="I",
        customer_id=cust,
        as_of=date(2026, 1, 1),
        amount=amount,
        terms_days=30,
        days_overdue_now=0,
        customer_prior_count=5,
        customer_late_rate=late_rate,
        customer_avg_overdue=late_rate * 20,
        is_cold_start=False,
    )
    return TrainingExample(features=f, label=label)


def _separable(n: int = 200) -> list[TrainingExample]:
    # customer_late_rate cleanly separates the classes, with a little overlap.
    out: list[TrainingExample] = []
    for i in range(n):
        late = i % 2 == 0
        rate = 0.85 if late else 0.1
        rate += 0.05 if i % 10 == 0 else 0.0  # mild noise
        out.append(_ex(late_rate=min(rate, 1.0), label=late, cust=f"C{i}"))
    return out


def test_predict_proba_is_bounded_and_deterministic() -> None:
    train = _separable()
    a = LatePaymentModel().fit(train).predict_proba(train)
    b = LatePaymentModel().fit(train).predict_proba(train)

    assert len(a) == len(train)
    assert all(0.0 <= p <= 1.0 for p in a)
    assert a == b  # random_state fixed -> reproducible
    assert len(FEATURE_NAMES) == 12  # 6 history + 6 Companies House


def test_model_learns_a_present_signal() -> None:
    data = _separable()
    y = [1 if e.label else 0 for e in data]
    scores = LatePaymentModel().fit(data).predict_proba(data)

    assert average_precision(y, scores) > prevalence(y) + 0.3


def test_single_class_training_falls_back_to_the_base_rate() -> None:
    all_late = [_ex(late_rate=0.9, label=True, cust=f"C{i}") for i in range(10)]
    model = LatePaymentModel().fit(all_late)

    preds = model.predict_proba(all_late[:3])
    assert preds == [1.0, 1.0, 1.0]  # base rate of an all-positive fold


def test_model_learns_from_companies_house_signals_alone() -> None:
    """History features identical everywhere; only the CH signals separate the
    classes. The fitted model must pick the signal up — this is the mechanism by
    which real CH data can lift the score past the history-only ceiling."""
    from cashflow_risk.enrichment.companies_house import CompanySignals

    def signals(number: str, *, distressed: bool) -> CompanySignals:
        return CompanySignals(
            company_number=number,
            status="active",
            accounts_overdue=distressed,
            accounts_next_due=None,
            confirmation_overdue=False,
            has_insolvency=distressed,
            has_charges=False,
        )

    data = []
    for i in range(200):
        late = i % 2 == 0
        base = _ex(late_rate=0.4, label=late, cust=f"C{i}")  # identical features
        noisy_clean = i % 20 == 0  # a few distressed-but-on-time, so it's not exact
        data.append(
            TrainingExample(
                features=base.features,
                label=late,
                signals=signals(synthetic_company_number(i), distressed=late != noisy_clean),
            )
        )

    y = [1 if e.label else 0 for e in data]
    scores = LatePaymentModel().fit(data).predict_proba(data)

    assert average_precision(y, scores) > prevalence(y) + 0.3


def test_examples_without_signals_still_score() -> None:
    with_sig = _separable(50)
    # None signals must be handled as "unknown", not crash or coerce to clean
    scores = LatePaymentModel().fit(with_sig).predict_proba(with_sig[:5])
    assert len(scores) == 5


def test_unfitted_model_and_empty_input() -> None:
    with pytest.raises(RuntimeError):
        LatePaymentModel().predict_proba(_separable(2))
    with pytest.raises(ValueError):
        LatePaymentModel().fit([])
    assert LatePaymentModel().fit(_separable()).predict_proba([]) == []
