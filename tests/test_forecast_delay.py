"""Behaviour of risk-driven payment-delay coupling.

Translates a late-payment risk signal into an expected payment delay (days after
due date), so the cash forecast and the invoice ranking are driven by the same
view of the world rather than telling two unrelated stories.
"""

from datetime import date, timedelta
from decimal import Decimal

from cashflow_risk.datagen.generator import GeneratorConfig, generate_dataset
from cashflow_risk.domain import Invoice, InvoiceStatus
from cashflow_risk.features.store import InvoiceFeatures, build_invoice_features
from cashflow_risk.forecasting.baselines import forecast_cash
from cashflow_risk.risk.forecast_delay import expected_delay_days, risk_adjusted_delay_fn


def _inv(invoice_id: str, customer_id: str = "C") -> Invoice:
    return Invoice(
        id=invoice_id,
        business_id="biz",
        customer_id=customer_id,
        amount=Decimal("1000"),
        issue_date=date(2026, 1, 1),
        due_date=date(2026, 1, 31),
    )


def _feat(**kw: object) -> InvoiceFeatures:
    defaults: dict[str, object] = dict(
        invoice_id="I",
        customer_id="C",
        as_of=date(2026, 3, 1),
        amount=1000.0,
        terms_days=30,
        days_overdue_now=0,
        customer_prior_count=4,
        customer_late_rate=0.0,
        customer_avg_overdue=0.0,
        is_cold_start=False,
    )
    defaults.update(kw)
    return InvoiceFeatures(**defaults)  # type: ignore[arg-type]


def test_chronic_late_payer_gets_a_longer_expected_delay() -> None:
    reliable = expected_delay_days(_feat(customer_avg_overdue=0.0, customer_late_rate=0.0), 0.1)
    chronic = expected_delay_days(_feat(customer_avg_overdue=25.0, customer_late_rate=0.8), 0.7)

    assert reliable == 0
    assert chronic > reliable


def test_expected_delay_is_never_earlier_than_current_overdue() -> None:
    f = _feat(days_overdue_now=40, customer_avg_overdue=10.0, customer_late_rate=0.5)

    assert expected_delay_days(f, 0.5) >= 40


def test_cold_start_delay_scales_with_probability() -> None:
    low = expected_delay_days(_feat(is_cold_start=True, customer_prior_count=0), 0.1)
    high = expected_delay_days(_feat(is_cold_start=True, customer_prior_count=0), 0.8)

    assert high > low


def test_delay_fn_maps_by_invoice_id_and_defaults_to_zero() -> None:
    feats = [_feat(invoice_id="A", customer_avg_overdue=20.0, customer_late_rate=0.6)]
    delay = risk_adjusted_delay_fn(feats)

    assert delay(_inv("A")) == 20
    assert delay(_inv("UNKNOWN")) == 0  # not scored -> paid on due date


def test_risk_adjusted_forecast_defers_inflows_versus_paid_on_time() -> None:
    ds = generate_dataset(GeneratorConfig(seed=1, n_customers=25))
    as_of = date(2025, 1, 1) + timedelta(weeks=30)

    features = build_invoice_features(ds.invoices, as_of=as_of)
    delay = risk_adjusted_delay_fn(features)

    open_snapshot = [
        inv.model_copy(
            update={"status": InvoiceStatus.OPEN, "paid_date": None, "amount_paid": Decimal("0")}
        )
        for inv in ds.invoices
        if inv.issue_date <= as_of and (inv.paid_date is None or inv.paid_date > as_of)
    ]
    common = dict(
        opening_balance=5000, as_of=as_of, invoices=open_snapshot, bills=[], obligations=[]
    )

    on_time = forecast_cash(**common, payment_delay_days=0)
    adjusted = forecast_cash(**common, payment_delay_days=delay)

    naive_inflows = [w.expected_inflow for w in on_time.weeks]
    adj_inflows = [w.expected_inflow for w in adjusted.weeks]

    assert naive_inflows != adj_inflows  # risk actually changed the timing
    # delays move cash later, so the first four weeks collect no more than before
    assert sum(adj_inflows[:4]) <= sum(naive_inflows[:4])
