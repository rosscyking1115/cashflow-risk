"""Rules-vs-logistic-vs-GBM bake-off over a purged rolling-origin backtest.

    uv run python scripts/bakeoff_risk.py [--track] [--tracking-uri URI]

Runs every scorer over identical walk-forward folds on synthetic data, across
seeds, and prints pooled PR-AUC (with lift over prevalence), top-decile precision,
calibration, and the cold-start slice — then a verdict against a pre-declared
margin.

The folds are **purged**: a training row whose 120-day label had not yet resolved
when the test window opened is dropped, because on the day the model would really
have been fitted that outcome was still unknown. The unpurged arm is printed
alongside on the *same* test windows, so the difference is the leak and nothing
else.

``--track`` logs every scorer x seed as an MLflow run (default store: a local
``sqlite:///mlflow.db`` — gitignored, no server), so the rules → logistic →
(maybe) LightGBM progression stays auditable. Tracking is training-time only:
mlflow-skinny comes from the ``train`` dependency group, never the runtime image.

Honest headline: on this generator, with the folds purged, **no fitted model beats
the rules baseline** — with or without Companies House signals, and gradient
boosting falls below prevalence. The printed "ceiling" row shows why. A *perfect*
observer of latent health (the oracle, read
straight from the latent table — allowed in a diagnostic script, never as a model
feature) only clears prevalence by ~0.10 mean lift on these folds: everything
else is the contemporaneous macro factor, which is unobservable at issue time
without leakage (docs/adr/0002). CH signals are a noisy subset of the health
ceiling, so no scorer can blow past it here. These are synthetic numbers — they
show the pipeline, folds and metrics work; they are not evidence of predictive
skill on real ledgers.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import timedelta

from cashflow_risk.datagen.generator import GeneratorConfig, generate_dataset
from cashflow_risk.risk.backtest import (
    BacktestResult,
    FitAndScore,
    Fold,
    rolling_origin_folds,
    run_backtest,
)
from cashflow_risk.risk.baseline import score_late_probability
from cashflow_risk.risk.dataset import TrainingExample, build_training_examples
from cashflow_risk.risk.model import LatePaymentModel

SEEDS = (1, 3, 7, 11, 42)
HORIZON_DAYS = 120
N_FOLDS = 4
MARGIN = 0.10  # pre-declared: the fitted rung must beat rules by this to earn its keep


def matched_folds(examples: list[TrainingExample]) -> tuple[list[Fold], list[Fold]]:
    """Purged folds, and the unpurged folds over the *same* test windows.

    Purging can leave an early fold with no trainable history, and that fold is
    dropped. Comparing against all four unpurged folds would then compare two
    different test sets, so the unpurged arm is restricted to the windows that
    survived. Any difference between the arms is the training-label overlap.
    """
    purged = rolling_origin_folds(examples, purge_days=HORIZON_DAYS, n_folds=N_FOLDS)
    windows = {id(f.test[0]) for f in purged}
    # purge_days=0 is the deliberately leaky arm — the only place in the project
    # that asks for one, and only so the leak can be measured against the purged run.
    unpurged = [
        f
        for f in rolling_origin_folds(examples, purge_days=0, n_folds=N_FOLDS)
        if f.test and id(f.test[0]) in windows
    ]
    return purged, unpurged


def _rules(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
    return [score_late_probability(e.features, e.signals).probability for e in test]


def _logistic(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
    return LatePaymentModel().fit(train).predict_proba(test)


def _gbm(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
    from cashflow_risk.risk.gbm import GradientBoostedModel  # train group only

    return GradientBoostedModel().fit(train).predict_proba(test)


def _scorers() -> list[tuple[str, FitAndScore]]:
    scorers: list[tuple[str, FitAndScore]] = [("rules", _rules), ("logistic", _logistic)]
    try:  # the GBM rung needs the train dependency group; skip cleanly without it
        import lightgbm  # noqa: F401

        scorers.append(("gbm", _gbm))
    except ImportError:
        print("(lightgbm not installed — gbm rung skipped; uv sync --group train)")
    return scorers


def _row(name: str, r: BacktestResult) -> str:
    p = r.pooled
    lift = p.average_precision - p.prevalence
    return (
        f"{name:>9}  {p.n:>5}  {p.prevalence:>6.3f}  {p.average_precision:>7.3f}  "
        f"{lift:>+6.3f}  {p.top_decile_precision:>7.3f}  {p.calibration_error:>6.3f}  "
        f"{r.cold_start.average_precision:>8.3f}"
    )


def _make_logger(tracking_uri: str) -> Callable[[str, int, BacktestResult], None]:
    """Build the MLflow logger. Imported lazily: without the ``train`` dependency
    group the bake-off still runs — only ``--track`` needs mlflow."""
    from cashflow_risk.risk.tracking import log_backtest

    def log(name: str, seed: int, result: BacktestResult) -> None:
        log_backtest(
            result,
            run_name=f"{name}-seed{seed}",
            params={
                "model": name,
                "seed": seed,
                "horizon_days": HORIZON_DAYS,
                "n_folds": N_FOLDS,
                "n_customers": 30,
                "weeks": 52,
            },
            tracking_uri=tracking_uri,
        )

    return log


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Rules-vs-logistic risk bake-off")
    parser.add_argument("--track", action="store_true", help="log runs to MLflow")
    parser.add_argument(
        "--tracking-uri",
        default="sqlite:///mlflow.db",
        help="MLflow tracking URI (default: local sqlite:///mlflow.db)",
    )
    args = parser.parse_args()
    log = _make_logger(args.tracking_uri) if args.track else None
    scorers = _scorers()

    print(f"\nRisk bake-off — rolling origin, issue-time, {HORIZON_DAYS}d horizon")
    print(f"Folds purged by {HORIZON_DAYS}d: a training row is dropped unless its label")
    print("had already resolved when the test window opened.")
    print("(synthetic data — pipeline check, not a predictive claim)")
    cols = ("model", "n", "prev", "PR-AUC", "lift", "top10%", "ECE", "cold-AP")
    widths = (9, 5, 6, 7, 6, 7, 6, 8)
    print("-" * 72)
    print("  ".join(f"{c:>{w}}" for c, w in zip(cols, widths, strict=True)))

    lifts: dict[str, list[float]] = {}
    leaky_lifts: dict[str, list[float]] = {}
    fold_counts: list[tuple[int, int]] = []
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
            purged, unpurged = matched_folds(examples)
            if not suffix:
                fold_counts.append(
                    (
                        len(rolling_origin_folds(examples, purge_days=0, n_folds=N_FOLDS)),
                        len(purged),
                    )
                )
            for name, scorer in scorers:
                key = name + suffix
                result = run_backtest(purged, scorer)
                lifts.setdefault(key, []).append(
                    result.pooled.average_precision - result.pooled.prevalence
                )
                leaky = run_backtest(unpurged, scorer)
                leaky_lifts.setdefault(key, []).append(
                    leaky.pooled.average_precision - leaky.pooled.prevalence
                )
                print(_row(key, result))
                if log is not None:
                    log(key, seed, result)
        purged_plain, _ = matched_folds(variants[""])
        ceiling = run_backtest(purged_plain, _oracle)
        lifts.setdefault("ceiling", []).append(
            ceiling.pooled.average_precision - ceiling.pooled.prevalence
        )
        print(_row("ceiling", ceiling))
        if log is not None:
            log("ceiling", seed, ceiling)

    print("-" * 72)
    means = {k: sum(v) / len(v) for k, v in lifts.items()}
    leaky_means = {k: sum(v) / len(v) for k, v in leaky_lifts.items()}
    print(
        "mean PR-AUC lift over prevalence — "
        + ", ".join(f"{k} {v:+.3f}" for k, v in means.items())
    )
    print(
        "\nSame test windows, unpurged training sets (what the label overlap was worth):"
    )
    for k in leaky_means:
        print(f"  {k:>12}  purged {means[k]:+.3f}   unpurged {leaky_means[k]:+.3f}"
              f"   delta {leaky_means[k] - means[k]:+.3f}")
    kept = ", ".join(f"{p}/{a}" for a, p in fold_counts)
    print(f"\nFolds kept after purging (per seed): {kept}")

    fitted = [k for k in means if k.endswith("+CH") and k != "rules+CH" and k != "ceiling"]
    best = max(fitted, key=lambda k: means[k])
    margin = means[best] - means["rules+CH"]
    verdict = "PASS" if margin >= MARGIN else "NOT MET"
    print(
        f"\nPre-declared margin (best fitted rung [{best}] beats rules+CH by "
        f">={MARGIN:.2f} pooled PR-AUC lift): {verdict} (margin {margin:+.3f}).\n"
        f"Context: the health-oracle ceiling is {means['ceiling']:+.3f} mean lift — the\n"
        "most ANY health-proxy (CH included) can extract from these folds; the rest\n"
        "of the signal is the issue-time-unobservable macro factor. Whether a fitted\n"
        "model earns its keep is decided on real data; these synthetic numbers are\n"
        "pipeline checks, not claims.\n"
    )


if __name__ == "__main__":
    main()
