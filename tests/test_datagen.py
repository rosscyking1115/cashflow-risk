"""Behaviour of the synthetic UK SME data generator.

The generator must produce data whose generative mechanism differs from what any
model is allowed to see (docs/adr/0002). These tests pin the statistical
properties that make the data non-trivial: customer concentration, persistent
per-customer payment behaviour, a right-skewed delay tail, and censoring.
"""

import numpy as np

from cashflow_risk.datagen.generator import GeneratorConfig, generate_dataset
from cashflow_risk.domain import Customer, Invoice, InvoiceStatus


def test_generates_a_coherent_dataset() -> None:
    ds = generate_dataset(GeneratorConfig(seed=1, n_customers=20))

    assert ds.business.country == "GB"
    assert len(ds.customers) == 20
    assert all(isinstance(c, Customer) for c in ds.customers)
    assert len(ds.invoices) > 0
    assert all(isinstance(i, Invoice) for i in ds.invoices)

    customer_ids = {c.id for c in ds.customers}
    assert all(i.customer_id in customer_ids for i in ds.invoices)
    assert all(i.business_id == ds.business.id for i in ds.invoices)


def test_same_seed_is_reproducible() -> None:
    a = generate_dataset(GeneratorConfig(seed=7))
    b = generate_dataset(GeneratorConfig(seed=7))

    def fingerprint(ds: object) -> list[tuple]:
        return [(i.id, i.amount, i.due_date, i.paid_date, i.status) for i in ds.invoices]

    assert fingerprint(a) == fingerprint(b)


def test_receivables_concentrate_in_a_few_customers() -> None:
    ds = generate_dataset(GeneratorConfig(seed=1, n_customers=25))

    by_customer: dict[str, float] = {c.id: 0.0 for c in ds.customers}
    for inv in ds.invoices:
        by_customer[inv.customer_id] += float(inv.amount)
    amounts = sorted(by_customer.values(), reverse=True)

    top_20pct = int(np.ceil(0.2 * len(amounts)))
    share = sum(amounts[:top_20pct]) / sum(amounts)
    assert share > 0.4  # well above the 0.2 a uniform split would give


def test_payment_behaviour_persists_with_latent_health() -> None:
    ds = generate_dataset(GeneratorConfig(seed=1, n_customers=25))

    per_customer = ds.latent.groupby("customer_id").agg(
        late=("paid_late", "mean"), health=("customer_health", "first")
    )
    # Spearman (rank-Pearson) — healthier customers pay late less often.
    rank_corr = per_customer["health"].rank().corr(per_customer["late"].rank())
    assert rank_corr < -0.3


def test_payment_delays_are_right_skewed() -> None:
    ds = generate_dataset(GeneratorConfig(seed=1))
    delays = ds.latent.loc[ds.latent["delay_days"] > 0, "delay_days"]

    assert delays.mean() > delays.median()  # heavy right tail


def test_some_invoices_are_censored_unpaid_at_horizon() -> None:
    ds = generate_dataset(GeneratorConfig(seed=1))

    open_invoices = [i for i in ds.invoices if i.status is InvoiceStatus.OPEN]
    assert len(open_invoices) >= 1
    assert all(i.paid_date is None for i in open_invoices)


def test_latent_truth_is_not_exposed_on_model_visible_entities() -> None:
    """Anti-circularity guard (docs/adr/0002): health/macro live only in the
    separate latent table, never on the entities a model would featurise."""
    ds = generate_dataset(GeneratorConfig(seed=1))

    assert "customer_health" not in Invoice.model_fields
    assert "customer_health" not in Customer.model_fields
    assert {"customer_health", "macro"} <= set(ds.latent.columns)
