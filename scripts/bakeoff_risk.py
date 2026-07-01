"""Rules-vs-logistic bake-off over a rolling-origin backtest (PLAN §7/§8.3).

    uv run python scripts/bakeoff_risk.py

Runs both scorers over identical walk-forward folds on synthetic data, across
seeds, and prints pooled PR-AUC (with lift over prevalence), top-decile precision,
calibration, and the cold-start slice — then a Gate-3 verdict.

Honest headline: on this generator the logistic model *ties* the rules baseline
at the pinned issue-time origin, because leakage-safe issue-time signal is weak by
construction (latent health is only sparsely estimable; the macro factor is not
observable at issue time — docs/adr/0002). The infrastructure is what matters: the
same folds and metrics will register a real win once Companies House distress
signals and richer history join the features on real data.
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
    return [score_late_probability(e.features).probability for e in test]


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

    rules_lifts: list[float] = []
    logit_lifts: list[float] = []
    for seed in SEEDS:
        cfg = GeneratorConfig(seed=seed, n_customers=30, weeks=52)
        ds = generate_dataset(cfg)
        observed_until = cfg.start + timedelta(days=cfg.weeks * 7)
        examples = build_training_examples(
            ds.invoices, horizon_days=HORIZON_DAYS, observed_until=observed_until
        )
        folds = rolling_origin_folds(examples, n_folds=N_FOLDS)

        rules = run_backtest(folds, _rules)
        logit = run_backtest(folds, _logistic)
        rules_lifts.append(rules.pooled.average_precision - rules.pooled.prevalence)
        logit_lifts.append(logit.pooled.average_precision - logit.pooled.prevalence)

        print(f"seed {seed}:")
        print(_row("rules", rules))
        print(_row("logistic", logit))

    print("-" * 72)
    mean_rules = sum(rules_lifts) / len(rules_lifts)
    mean_logit = sum(logit_lifts) / len(logit_lifts)
    print(f"mean PR-AUC lift over prevalence — rules {mean_rules:+.3f}, logistic {mean_logit:+.3f}")
    verdict = "PASS" if mean_logit - mean_rules >= 0.10 else "NOT MET"
    print(
        f"\nGate 3 (logistic beats rules by >=0.10 pooled PR-AUC lift): {verdict}.\n"
        "Expected on synthetic data — issue-time signal is weak by construction. The\n"
        "harness is ready to register a win once real Companies House distress signals\n"
        "and richer history join the features.\n"
    )


if __name__ == "__main__":
    main()
