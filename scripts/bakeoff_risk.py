"""Rules-vs-logistic bake-off over a rolling-origin backtest (PLAN §7/§8.3).

    uv run python scripts/bakeoff_risk.py

Runs both scorers over identical walk-forward folds on synthetic data, across
seeds, and prints pooled PR-AUC (with lift over prevalence), top-decile precision,
calibration, and the cold-start slice — then a Gate-3 verdict.

Honest headline: on this generator the fitted model ties or narrowly beats the
rules baseline, with or without Companies House signals — and the printed
"ceiling" row shows why. A *perfect* observer of latent health (the oracle, read
straight from the latent table — allowed in a diagnostic script, never as a model
feature) only clears prevalence by ~0.10 mean lift on these folds: everything
else is the contemporaneous macro factor, which is unobservable at issue time
without leakage (docs/adr/0002). CH signals are a noisy subset of the health
ceiling, so no scorer can blow past it here. Gate 3 is therefore decided on real
data (PLAN §8.3); this bake-off proves the pipeline, folds, and metrics work.
"""

from __future__ import annotations

import sys
from datetime import timedelta

from cashflow_risk.datagen.generator import GeneratorConfig, generate_dataset
from cashflow_risk.risk.backtest import BacktestResult, rolling_origin_folds, run_backtest
from cashflow_risk.risk.baseline import score_late_probability
from cashflow_risk.risk.dataset import TrainingExample, build_training_examples
from cashflow_risk.risk.model import LatePaymentModel

SEEDS = (1, 3, 7, 11, 42)
HORIZON_DAYS = 120
N_FOLDS = 4


def _rules(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
    return [score_late_probability(e.features, e.signals).probability for e in test]


def _logistic(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
    return LatePaymentModel().fit(train).predict_proba(test)


def _row(name: str, r: BacktestResult) -> str:
    p = r.pooled
    lift = p.average_precision - p.prevalence
    return (
        f"{name:>9}  {p.n:>5}  {p.prevalence:>6.3f}  {p.average_precision:>7.3f}  "
        f"{lift:>+6.3f}  {p.top_decile_precision:>7.3f}  {p.calibration_error:>6.3f}  "
        f"{r.cold_start.average_precision:>8.3f}"
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print(f"\nRisk bake-off — {N_FOLDS}-fold rolling origin, issue-time, {HORIZON_DAYS}d horizon")
    print("(synthetic data — pipeline check, not a predictive claim)")
    cols = ("model", "n", "prev", "PR-AUC", "lift", "top10%", "ECE", "cold-AP")
    widths = (9, 5, 6, 7, 6, 7, 6, 8)
    print("-" * 72)
    print("  ".join(f"{c:>{w}}" for c, w in zip(cols, widths, strict=True)))

    lifts: dict[str, list[float]] = {}
    for seed in SEEDS:
        cfg = GeneratorConfig(seed=seed, n_customers=30, weeks=52)
        ds = generate_dataset(cfg)
        observed_until = cfg.start + timedelta(days=cfg.weeks * 7)

        # identical invoices; the only difference is whether CH signals are seen
        variants = {
            "": build_training_examples(
                ds.invoices, horizon_days=HORIZON_DAYS, observed_until=observed_until
            ),
            "+CH": build_training_examples(
                ds.invoices,
                horizon_days=HORIZON_DAYS,
                observed_until=observed_until,
                signals=ds.company_signals,
            ),
        }

        # the health oracle: the generator's own latent truth, as an upper bound
        # on what any health-proxy (CH included) could ever extract from these folds
        health = {
            str(row["invoice_id"]): float(row["customer_health"])
            for _, row in ds.latent.iterrows()
        }

        def _oracle(
            train: list[TrainingExample],
            test: list[TrainingExample],
            health: dict[str, float] = health,  # bind per seed (B023)
        ) -> list[float]:
            return [1.0 - health[e.features.invoice_id] for e in test]

        print(f"seed {seed}:")
        for suffix, examples in variants.items():
            folds = rolling_origin_folds(examples, n_folds=N_FOLDS)
            for name, scorer in (("rules", _rules), ("logistic", _logistic)):
                result = run_backtest(folds, scorer)
                key = name + suffix
                lift = result.pooled.average_precision - result.pooled.prevalence
                lifts.setdefault(key, []).append(lift)
                print(_row(key, result))
        ceiling = run_backtest(rolling_origin_folds(variants[""], n_folds=N_FOLDS), _oracle)
        lifts.setdefault("ceiling", []).append(
            ceiling.pooled.average_precision - ceiling.pooled.prevalence
        )
        print(_row("ceiling", ceiling))

    print("-" * 72)
    means = {k: sum(v) / len(v) for k, v in lifts.items()}
    print(
        "mean PR-AUC lift over prevalence — "
        + ", ".join(f"{k} {v:+.3f}" for k, v in means.items())
    )
    margin = means["logistic+CH"] - means["rules+CH"]
    verdict = "PASS" if margin >= 0.10 else "NOT MET"
    print(
        f"\nGate 3 (logistic+CH beats rules+CH by >=0.10 pooled PR-AUC lift): "
        f"{verdict} (margin {margin:+.3f}).\n"
        f"Context: the health-oracle ceiling is {means['ceiling']:+.3f} mean lift — the\n"
        "most ANY health-proxy (CH included) can extract from these folds; the rest\n"
        "of the signal is the issue-time-unobservable macro factor. Gate 3 is decided\n"
        "on real data; synthetic numbers are pipeline checks, not claims.\n"
    )


if __name__ == "__main__":
    main()
