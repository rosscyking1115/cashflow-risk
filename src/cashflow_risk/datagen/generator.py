"""Synthetic UK SME data generator.

Built from a **latent mechanism the model is never given** (see
``docs/adr/0002-anti-circular-synthetic-data.md``):

- each Customer has a persistent latent *payment health* in (0, 1) — higher pays
  more reliably — which drives every one of their invoices (autocorrelation);
- a shared *macro factor* (an AR(1) series over weeks) makes late payments
  cluster in time, as they do in a downturn;
- payment delays are drawn from a heavy-tailed (lognormal) distribution, more
  variable for lower-health customers (heteroscedastic);
- Customer sizes follow a power law, so receivables concentrate in a few names;
- invoices whose payment date falls past the horizon are left unpaid (censored);
- a fraction of customers are incorporated (limited companies): their invoices
  carry a company identifier, and synthetic Companies House signals are derived
  from latent health *plus noise* — a partial, public-register observation of
  health, which is exactly what real CH data is to real payment behaviour.

Those identifiers are **deliberately non-resolvable** (``SYNTH-0007``, not
``10000007``) because the signals attached to them are fabricated. Distress flags
invented by a random number generator must not name a real company, and an
identifier that merely looks unused is not safe — see
:data:`SYNTHETIC_NUMBER_PREFIX`.

The latent truth (health, macro, draw probabilities) is returned in a *separate*
``latent`` table for analysis and generator validation — it must never be fed to
a model as a feature. Signal randomness comes from its own rng, so the invoice
stream is identical with signals on or off (clean A/B for bake-offs).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from cashflow_risk.domain import Business, Customer, Invoice, InvoiceStatus
from cashflow_risk.enrichment.companies_house import CompanySignals

_TERMS = np.array([14, 30, 60])
_TERMS_PROBS = np.array([0.2, 0.6, 0.2])
_AR1_PHI = 0.7

# Synthetic customers carry a deliberately **non-resolvable** company identifier.
#
# A real Companies House number is exactly eight alphanumeric characters — eight
# digits, or a two-letter prefix and six digits (SC, NI, OC, SO and friends). This
# format is ten characters and contains a hyphen, which no Companies House format
# permits, so it cannot collide on shape rather than merely on an unissued range.
# That distinction is the whole point: ranges get issued.
#
# This generator previously used ``f"{10000000 + i:08d}"``, which produced
# 10000000–10000029. Those are real, currently-registered UK companies, and the
# generator was attaching fabricated insolvency and overdue-filing flags to them.
SYNTHETIC_NUMBER_PREFIX = "SYNTH"


def synthetic_company_number(index: int) -> str:
    """A company identifier that cannot resolve on the public register.

    Args:
        index: The customer's position in the generated set.

    Returns:
        An identifier of the form ``SYNTH-0007`` — structurally invalid as a
        Companies House number, so it can never name a real company.
    """
    return f"{SYNTHETIC_NUMBER_PREFIX}-{index:04d}"


@dataclass(frozen=True)
class GeneratorConfig:
    """Parameters for a reproducible synthetic dataset. Seeded end to end."""

    seed: int = 0
    n_customers: int = 25
    start: date = date(2025, 1, 1)
    weeks: int = 52
    invoices_per_week: float = 10.0
    mean_invoice_amount: float = 2500.0
    pareto_shape: float = 1.5  # smaller => more customer concentration
    horizon: date | None = None  # censoring point; defaults to start + weeks
    incorporated_frac: float = 0.6  # fraction of customers that are ltd companies


@dataclass(frozen=True)
class SyntheticDataset:
    """A generated Business with its Customers and Invoices.

    ``latent`` holds the ground-truth generative variables (per invoice). It is
    for analysis only and must not be used as model features. ``company_signals``
    maps an incorporated customer's company identifier to its synthetic Companies
    House signals — a *noisy* observation of latent health that models may see.

    The identifiers are non-resolvable by construction
    (:func:`synthetic_company_number`); nothing here names a real company.
    """

    business: Business
    customers: list[Customer]
    invoices: list[Invoice]
    latent: pd.DataFrame
    company_signals: dict[str, CompanySignals]


def _synthetic_signals(rng: np.random.Generator, number: str, health: float) -> CompanySignals:
    """Companies House signals as a noisy function of latent health.

    Distress probabilities fall with health, and every field is an independent
    draw — the signals *inform about* health without revealing it, mirroring how
    real filings relate to real financial trouble.
    """
    return CompanySignals(
        company_number=number,
        status="active",
        accounts_overdue=bool(rng.random() < np.clip(0.75 - 0.9 * health, 0.03, 0.85)),
        accounts_next_due=None,
        confirmation_overdue=bool(rng.random() < np.clip(0.5 - 0.6 * health, 0.02, 0.6)),
        has_insolvency=bool(rng.random() < max(0.0, 0.35 - 0.7 * health)),
        has_charges=bool(rng.random() < 0.15 + 0.25 * (1.0 - health)),
    )


def _macro_series(rng: np.random.Generator, weeks: int) -> np.ndarray:
    """An AR(1) economic factor; positive values mean tougher conditions."""
    eps = rng.normal(0.0, 1.0, weeks)
    macro = np.empty(weeks)
    macro[0] = eps[0]
    scale = np.sqrt(1.0 - _AR1_PHI**2)
    for t in range(1, weeks):
        macro[t] = _AR1_PHI * macro[t - 1] + scale * eps[t]
    return macro


def generate_dataset(config: GeneratorConfig) -> SyntheticDataset:
    rng = np.random.default_rng(config.seed)
    n = config.n_customers
    horizon = config.horizon or (config.start + timedelta(days=config.weeks * 7))

    business = Business(id="biz_synth", name="Synthetic Trading Ltd", sector="services")

    # --- latent customer attributes (never exposed as features) ---
    sizes = rng.pareto(config.pareto_shape, n) + 1.0  # heavy-tailed, >= 1
    weights = sizes / sizes.sum()
    health = rng.beta(2.0, 2.0, n)  # persistent payment reliability in (0, 1)
    terms = rng.choice(_TERMS, n, p=_TERMS_PROBS)

    customers = [
        Customer(
            id=f"cust_{i:03d}",
            business_id=business.id,
            name=f"Customer {i:03d}",
            payment_terms_days=int(terms[i]),
        )
        for i in range(n)
    ]

    macro = _macro_series(rng, config.weeks)

    # --- Companies House world (separate rng: the invoice stream above and below
    # is bit-identical whether signals are on or off — a clean A/B) ---
    rng_signals = np.random.default_rng([config.seed, 813])
    incorporated = rng_signals.random(n) < config.incorporated_frac
    # Deliberately non-resolvable identifiers — see SYNTHETIC_NUMBER_PREFIX.
    company_numbers: dict[int, str] = {
        i: synthetic_company_number(i) for i in range(n) if incorporated[i]
    }
    company_signals = {
        number: _synthetic_signals(rng_signals, number, float(health[i]))
        for i, number in company_numbers.items()
    }

    invoices: list[Invoice] = []
    latent_rows: list[dict[str, object]] = []
    counter = 0

    for w in range(config.weeks):
        week_start = config.start + timedelta(days=7 * w)
        for _ in range(int(rng.poisson(config.invoices_per_week))):
            c = int(rng.choice(n, p=weights))
            issue = week_start + timedelta(days=int(rng.integers(0, 7)))
            due = issue + timedelta(days=int(terms[c]))

            size_ratio = sizes[c] / sizes.mean()
            amount = float(rng.lognormal(np.log(config.mean_invoice_amount * size_ratio), 0.5))
            amount = max(50.0, amount)

            # probability this invoice is paid late, driven by latent health + macro
            logit = 0.3 - 2.5 * health[c] + 1.2 * macro[w]
            p_late = 1.0 / (1.0 + np.exp(-logit))
            is_late = bool(rng.random() < p_late)
            if is_late:
                sigma = 0.5 + (1.0 - health[c])  # lower health => more variable
                delay = min(float(rng.lognormal(2.0, sigma)), 365.0)
            else:
                delay = 0.0
            pay_date = due + timedelta(days=int(round(delay)))

            inv_id = f"INV-{1000 + counter}"
            counter += 1
            amount_dec = Decimal(str(round(amount, 2)))

            if pay_date <= horizon:
                invoice = Invoice(
                    id=inv_id,
                    business_id=business.id,
                    customer_id=customers[c].id,
                    amount=amount_dec,
                    issue_date=issue,
                    due_date=due,
                    paid_date=pay_date,
                    amount_paid=amount_dec,
                    status=InvoiceStatus.PAID,
                    company_number=company_numbers.get(c),
                )
                paid = True
            else:
                invoice = Invoice(
                    id=inv_id,
                    business_id=business.id,
                    customer_id=customers[c].id,
                    amount=amount_dec,
                    issue_date=issue,
                    due_date=due,
                    status=InvoiceStatus.OPEN,
                    company_number=company_numbers.get(c),
                )
                paid = False

            invoices.append(invoice)
            latent_rows.append(
                {
                    "invoice_id": inv_id,
                    "customer_id": customers[c].id,
                    "week": w,
                    "customer_health": float(health[c]),
                    "macro": float(macro[w]),
                    "p_late": float(p_late),
                    "delay_days": float(delay),
                    "paid_late": bool(is_late),
                    "paid": paid,
                }
            )

    latent = pd.DataFrame(latent_rows)
    return SyntheticDataset(
        business=business,
        customers=customers,
        invoices=invoices,
        latent=latent,
        company_signals=company_signals,
    )
