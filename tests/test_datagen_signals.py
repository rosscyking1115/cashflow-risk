"""Synthetic Companies House signals in the generator.

The thesis under test: CH distress signals are a *noisy observation* of the
latent payment health the model is never given (docs/adr/0002). The generator
marks a fraction of customers as incorporated, stamps their invoices with a
company number, and derives signals from health + noise — so a model that reads
the signals gets a partial view of health without ever seeing health itself.
"""

from cashflow_risk.datagen.generator import GeneratorConfig, generate_dataset
from cashflow_risk.enrichment.companies_house import CompanySignals


def test_only_incorporated_customers_get_company_numbers_and_signals() -> None:
    ds = generate_dataset(GeneratorConfig(seed=1, n_customers=40, incorporated_frac=0.6))

    stamped = {i.company_number for i in ds.invoices if i.company_number}
    unstamped = [i for i in ds.invoices if i.company_number is None]

    assert stamped  # some incorporated customers
    assert unstamped  # some sole traders — CH never covers them
    # every stamped number has signals (some incorporated customers may simply
    # never have drawn an invoice, so the dict can be a superset)
    assert stamped <= set(ds.company_signals.keys())
    assert all(isinstance(s, CompanySignals) for s in ds.company_signals.values())


def test_incorporated_frac_zero_means_no_signals() -> None:
    ds = generate_dataset(GeneratorConfig(seed=1, n_customers=20, incorporated_frac=0.0))

    assert ds.company_signals == {}
    assert all(i.company_number is None for i in ds.invoices)


def test_signals_do_not_perturb_the_invoice_stream() -> None:
    """Signal randomness is drawn from a separate rng, so the ±signals worlds
    share identical invoices — a clean A/B for the bake-off."""
    without = generate_dataset(GeneratorConfig(seed=7, incorporated_frac=0.0))
    with_ = generate_dataset(GeneratorConfig(seed=7, incorporated_frac=0.6))

    def fingerprint(ds: object) -> list[tuple]:
        return [
            (i.id, i.customer_id, i.amount, i.issue_date, i.due_date, i.paid_date)
            for i in ds.invoices  # type: ignore[attr-defined]
        ]

    assert fingerprint(without) == fingerprint(with_)


def test_distress_signals_track_low_latent_health() -> None:
    ds = generate_dataset(GeneratorConfig(seed=3, n_customers=200, incorporated_frac=1.0))

    health = ds.latent.groupby("customer_id")["customer_health"].first()
    number_of = {i.customer_id: i.company_number for i in ds.invoices if i.company_number}

    low = [c for c in number_of if c in health.index and health[c] < 0.35]
    high = [c for c in number_of if c in health.index and health[c] > 0.65]
    assert len(low) > 10 and len(high) > 10

    def overdue_rate(customers: list[str]) -> float:
        signals = [ds.company_signals[number_of[c]] for c in customers]
        return sum(1 for s in signals if s.accounts_overdue) / len(signals)

    # noisy, but clearly ordered: struggling companies show distress more often
    assert overdue_rate(low) > overdue_rate(high) + 0.2


def test_signals_never_carry_the_latent_truth() -> None:
    """Anti-circularity: a CompanySignals row holds public-register facts only."""
    fields = set(CompanySignals.__dataclass_fields__)
    assert "customer_health" not in fields
    assert "macro" not in fields
    assert "p_late" not in fields
