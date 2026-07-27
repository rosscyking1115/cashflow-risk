"""Baseline evaluation report for the late-payment risk model.

    uv run python scripts/eval_risk_baseline.py

Scores the transparent rules baseline over credibly-generated synthetic data at
the *pinned* prediction origin (the invoice issue date), across several
seeds, and prints PR-AUC vs prevalence, top-decile precision, and calibration.

The headline is deliberately honest: at issue-time origin the rules baseline sits
close to the prevalence line — the customer's observed prior late-rate is a weak,
sparse proxy for the latent payment health + macro factor the generator uses and
never reveals (docs/adr/0002). That near-prevalence number is the floor any
fitted model (logistic → LightGBM) with macro or Companies House features must
beat.
Synthetic metrics are pipeline checks, not predictive claims (only real data is).
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

from cashflow_risk.datagen.generator import GeneratorConfig, generate_dataset
from cashflow_risk.risk.baseline import score_late_probability
from cashflow_risk.risk.dataset import build_training_examples
from cashflow_risk.risk.evaluation import RiskEvaluation, evaluate

HORIZON_DAYS = 120
SEEDS = (1, 3, 7, 11, 42)


def _report_for_seed(seed: int) -> RiskEvaluation:
    cfg = GeneratorConfig(seed=seed, n_customers=30, weeks=52)
    ds = generate_dataset(cfg)
    observed_until = cfg.start + timedelta(days=cfg.weeks * 7)
    examples = build_training_examples(
        ds.invoices, horizon_days=HORIZON_DAYS, observed_until=observed_until
    )
    y = [1 if e.label else 0 for e in examples]
    scores = [score_late_probability(e.features).probability for e in examples]
    # chase ~10 invoices/week over the ~52-week window -> a realistic top-k budget
    return evaluate(y, scores, chase_capacity=max(1, round(0.1 * len(examples))))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print(f"\nRules-baseline evaluation — issue-time origin, horizon {HORIZON_DAYS}d")
    print(f"(as of {date.today():%d %b %Y}; synthetic data — pipeline check, not a claim)")
    print("-" * 74)
    cols = ("seed", "n", "prev", "PR-AUC", "lift", "top10%", "ECE")
    widths = (5, 5, 6, 7, 6, 7, 6)
    print("  ".join(f"{c:>{w}}" for c, w in zip(cols, widths, strict=True)))

    reports = []
    for seed in SEEDS:
        r = _report_for_seed(seed)
        reports.append(r)
        lift = r.average_precision - r.prevalence
        print(
            f"{seed:>5}  {r.n:>5}  {r.prevalence:>6.3f}  {r.average_precision:>7.3f}  "
            f"{lift:>+6.3f}  {r.top_decile_precision:>7.3f}  {r.calibration_error:>6.3f}"
        )

    mean_lift = sum(r.average_precision - r.prevalence for r in reports) / len(reports)
    print("-" * 74)
    print(f"mean PR-AUC lift over prevalence: {mean_lift:+.3f}")
    print(
        "\nNear-zero lift is expected and is the point: at issue time the rules\n"
        "baseline has only sparse customer history to go on. This is the floor the\n"
        "fitted model with macro or Companies House features must beat.\n"
    )


if __name__ == "__main__":
    main()
