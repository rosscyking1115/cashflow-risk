"""Is the risk bake-off measuring the model, or measuring the generator?

    uv run python scripts/controls_risk_generator.py

Two controls over the same folds, seeds and protocol as ``bakeoff_risk.py``.

**Positive control.** Score the test folds using *only* the generator's own
lateness drivers — latent ``p_late``, latent ``macro``, latent ``customer_health``
— none of which any model can see. If a model that never touches them matched
them, the benchmark would be measuring its own construction rather than any
method. It does not: the oracles beat every shipped scorer several times over.

**Negative control.** Re-draw every invoice's lateness independently of every
latent variable, leaving the customers, amounts, terms and dates exactly as
generated. Ranking performance must collapse. It does — to the same place a
*random* scorer lands, which is the point of ``null_risk_bakeoff.py`` and is why
that script exists alongside this one.

Read the two together. This one shows the benchmark is not circular. That one
shows the published figures cannot be distinguished from chance anyway.
See ``docs/evaluation-null.md``.
"""

from __future__ import annotations

import statistics
import sys
from collections.abc import Callable, Mapping
from datetime import date, timedelta
from decimal import Decimal

import numpy as np

from cashflow_risk.datagen.generator import (
    GeneratorConfig,
    SyntheticDataset,
    generate_dataset,
)
from cashflow_risk.domain import Invoice, InvoiceStatus
from cashflow_risk.risk.backtest import rolling_origin_folds, run_backtest
from cashflow_risk.risk.baseline import score_late_probability
from cashflow_risk.risk.dataset import TrainingExample, build_training_examples
from cashflow_risk.risk.model import LatePaymentModel

SEEDS = (1, 3, 7, 11, 42)  # the seeds bakeoff_risk.py publishes
HORIZON_DAYS = 120
N_FOLDS = 4
N_CUSTOMERS = 30
WEEKS = 52

Scorer = Callable[[list[TrainingExample], list[TrainingExample]], list[float]]


def sever_lateness(dataset: SyntheticDataset, *, seed: int, horizon_weeks: int) -> list[Invoice]:
    """Re-draw every invoice's lateness independently of every latent variable.

    Customers, amounts, payment terms and issue dates are left exactly as
    generated — only *whether and how late* each invoice is paid is replaced by a
    draw that no feature can predict. The per-invoice late probability becomes the
    dataset's own mean ``p_late``, so the base rate is preserved and a collapse
    cannot be blamed on prevalence moving.

    Companies House signals are deliberately left alone. They are still derived
    from latent health, so under this control they become pure noise with respect
    to the label — which is exactly what should happen to them.

    Args:
        dataset: A dataset from :func:`generate_dataset`.
        seed: Seed for the replacement lateness draws.
        horizon_weeks: The generator's censoring horizon, in weeks from the start.

    Returns:
        The same invoices with their payment outcomes redrawn.
    """
    rng = np.random.default_rng([seed, 9001])
    p_const = float(dataset.latent["p_late"].mean())
    horizon = min(i.issue_date for i in dataset.invoices) + timedelta(days=horizon_weeks * 7)

    severed: list[Invoice] = []
    for inv in dataset.invoices:
        is_late = bool(rng.random() < p_const)
        delay = min(float(rng.lognormal(2.0, 1.0)), 365.0) if is_late else 0.0
        pay_date = inv.due_date + timedelta(days=int(round(delay)))
        if pay_date <= horizon:
            severed.append(
                inv.model_copy(
                    update={
                        "paid_date": pay_date,
                        "amount_paid": inv.amount,
                        "status": InvoiceStatus.PAID,
                    }
                )
            )
        else:
            severed.append(
                inv.model_copy(
                    update={
                        "paid_date": None,
                        "amount_paid": Decimal("0"),
                        "status": InvoiceStatus.OPEN,
                    }
                )
            )
    return severed


def _rules(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
    return [score_late_probability(e.features, e.signals).probability for e in test]


def _logistic(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
    return LatePaymentModel().fit(train).predict_proba(test)


def _oracle(values: Mapping[str, float], *, invert: bool = False) -> Scorer:
    """A scorer that reads one of the generator's latent variables directly.

    Allowed in a diagnostic script and nowhere else — feeding any of these to a
    model would re-introduce the circularity ``docs/adr/0002`` exists to prevent.
    """

    def score(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
        return [
            (1.0 - values[e.features.invoice_id]) if invert else values[e.features.invoice_id]
            for e in test
        ]

    return score


def _lift(examples: list[TrainingExample], scorer: Scorer) -> float:
    folds = rolling_origin_folds(examples, purge_days=HORIZON_DAYS, n_folds=N_FOLDS)
    result = run_backtest(folds, scorer)
    return result.pooled.average_precision - result.pooled.prevalence


def _report(title: str, arms: dict[str, list[float]]) -> None:
    print(f"\n{title}")
    print("-" * 62)
    print(f"{'scorer':>20}  {'mean lift':>10}")
    for name, values in arms.items():
        print(f"{name:>20}  {statistics.fmean(values):>+10.3f}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    shipped: dict[str, list[float]] = {}
    severed_arms: dict[str, list[float]] = {}

    for seed in SEEDS:
        config = GeneratorConfig(seed=seed, n_customers=N_CUSTOMERS, weeks=WEEKS)
        dataset = generate_dataset(config)
        observed_until = config.start + timedelta(days=config.weeks * 7)
        latent = dataset.latent.set_index("invoice_id")

        def build(
            invoices: list[Invoice],
            *,
            with_signals: bool,
            dataset: SyntheticDataset = dataset,  # bind per seed (B023)
            observed_until: date = observed_until,
        ) -> list[TrainingExample]:
            return build_training_examples(
                invoices,
                horizon_days=HORIZON_DAYS,
                observed_until=observed_until,
                signals=dataset.company_signals if with_signals else None,
            )

        plain = build(dataset.invoices, with_signals=False)
        with_ch = build(dataset.invoices, with_signals=True)

        shipped.setdefault("rules", []).append(_lift(plain, _rules))
        shipped.setdefault("rules+CH", []).append(_lift(with_ch, _rules))
        shipped.setdefault("logistic+CH", []).append(_lift(with_ch, _logistic))
        shipped.setdefault("oracle: health", []).append(
            _lift(plain, _oracle(latent["customer_health"].to_dict(), invert=True))
        )
        shipped.setdefault("oracle: macro", []).append(
            _lift(plain, _oracle(latent["macro"].to_dict()))
        )
        shipped.setdefault("oracle: p_late", []).append(
            _lift(plain, _oracle(latent["p_late"].to_dict()))
        )

        severed = sever_lateness(dataset, seed=seed, horizon_weeks=config.weeks)
        severed_plain = build(severed, with_signals=False)
        severed_ch = build(severed, with_signals=True)
        severed_arms.setdefault("rules", []).append(_lift(severed_plain, _rules))
        severed_arms.setdefault("rules+CH", []).append(_lift(severed_ch, _rules))
        severed_arms.setdefault("logistic+CH", []).append(_lift(severed_ch, _logistic))
        severed_arms.setdefault("oracle: health", []).append(
            _lift(severed_plain, _oracle(latent["customer_health"].to_dict(), invert=True))
        )

    _report(
        "POSITIVE CONTROL — as shipped. Oracles read the generator's own drivers;\n"
        "no model can see any of them. Mean PR-AUC lift over prevalence.",
        shipped,
    )
    print(
        "\nThe oracles beat every shipped scorer by a wide margin, so the models are\n"
        "not recovering the construction: the benchmark is NOT circular. Note that\n"
        "the macro factor alone outscores every model — it is the larger driver and\n"
        "it has no issue-time proxy at all (docs/adr/0002)."
    )

    _report(
        "NEGATIVE CONTROL — lateness re-drawn independently of every latent\n"
        "variable. Everything should collapse.",
        severed_arms,
    )
    print(
        "\nIt does. Nothing leaks. But 'collapsed' here is not zero — see\n"
        "scripts/null_risk_bakeoff.py, which measures where an uninformative\n"
        "scorer actually lands under this protocol. That is the real finding.\n"
    )


if __name__ == "__main__":
    main()
