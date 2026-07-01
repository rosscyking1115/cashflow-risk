"""Leakage-safe training-example builder for the risk model.

Each example fixes the prediction origin at the invoice's issue date, builds
as-of-issue features (never consulting the eventual payment), and attaches the
pinned label resolved at issue_date + horizon.
"""

from datetime import date, timedelta
from decimal import Decimal

from cashflow_risk.datagen.generator import GeneratorConfig, generate_dataset
from cashflow_risk.domain import Invoice, InvoiceStatus
from cashflow_risk.risk.dataset import build_training_examples
from cashflow_risk.risk.evaluation import average_precision, prevalence


def _inv(inv_id: str, customer: str, *, issue: date, due: date, paid: date | None) -> Invoice:
    status = InvoiceStatus.PAID if paid is not None else InvoiceStatus.OPEN
    return Invoice(
        id=inv_id,
        business_id="B",
        customer_id=customer,
        amount=Decimal("1000"),
        issue_date=issue,
        due_date=due,
        paid_date=paid,
        amount_paid=Decimal("1000") if paid else Decimal("0"),
        status=status,
    )


def test_one_example_per_invoice_with_as_of_issue_features() -> None:
    invoices = [
        _inv("A", "C1", issue=date(2026, 1, 1), due=date(2026, 1, 31), paid=date(2026, 1, 20)),
        _inv("B", "C1", issue=date(2026, 3, 1), due=date(2026, 3, 31), paid=date(2026, 5, 1)),
    ]
    examples = build_training_examples(invoices, horizon_days=120)

    assert {e.features.invoice_id for e in examples} == {"A", "B"}
    b = next(e for e in examples if e.features.invoice_id == "B")
    # as-of B's issue date, A is a prior settled (on-time) invoice for C1
    assert b.features.as_of == date(2026, 3, 1)
    assert b.features.customer_prior_count == 1
    assert b.features.customer_late_rate == 0.0
    assert b.features.is_cold_start is False
    # days_overdue at issue is always 0 (never leaks the outcome)
    assert b.features.days_overdue_now == 0


def test_label_is_resolved_at_issue_plus_horizon() -> None:
    # paid 30 days late; with a short horizon the payment is unseen -> positive
    inv = _inv("A", "C1", issue=date(2026, 1, 1), due=date(2026, 1, 31), paid=date(2026, 3, 2))
    short = build_training_examples([inv], horizon_days=40)  # horizon 2026-02-10, still open
    long = build_training_examples([inv], horizon_days=120)  # horizon 2026-05-01, paid & late

    assert short[0].label is True  # unpaid at horizon
    assert long[0].label is True  # paid, but 30 days late
    on_time = _inv("A", "C1", issue=date(2026, 1, 1), due=date(2026, 1, 31), paid=date(2026, 1, 25))
    assert build_training_examples([on_time], horizon_days=120)[0].label is False


def test_observed_until_drops_examples_whose_label_is_not_yet_resolvable() -> None:
    invoices = [
        _inv("EARLY", "C1", issue=date(2026, 1, 1), due=date(2026, 1, 31), paid=None),
        _inv("LATE", "C2", issue=date(2026, 6, 1), due=date(2026, 7, 1), paid=None),
    ]
    # horizon 90d: EARLY resolves 2026-04-01, LATE resolves 2026-08-30.
    examples = build_training_examples(
        invoices, horizon_days=90, observed_until=date(2026, 5, 1)
    )
    # LATE's outcome is unobservable as-of 2026-05-01, so it is excluded.
    assert {e.features.invoice_id for e in examples} == {"EARLY"}


def test_harness_detects_a_latent_signal_it_should_beat_prevalence() -> None:
    # The generator's latent p_late is the oracle score. On observable examples it
    # must clear prevalence by a wide margin — proving the label builder + metric
    # measure real discrimination (the rules baseline, by contrast, sits near the
    # prevalence line at issue-time origin; see scripts/eval_risk_baseline.py).
    ds = generate_dataset(GeneratorConfig(seed=7, n_customers=30, weeks=52))
    censor = date(2025, 1, 1) + timedelta(days=52 * 7)
    examples = build_training_examples(ds.invoices, horizon_days=120, observed_until=censor)
    p_late = {row["invoice_id"]: float(row["p_late"]) for _, row in ds.latent.iterrows()}

    y = [1 if e.label else 0 for e in examples]
    oracle = [p_late[e.features.invoice_id] for e in examples]

    assert len(examples) > 100
    assert 0.0 < prevalence(y) < 1.0
    assert average_precision(y, oracle) > prevalence(y) + 0.15
