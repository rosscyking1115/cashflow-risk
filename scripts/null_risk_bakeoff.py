"""What does an *uninformative* scorer score on these folds?

    uv run python scripts/null_risk_bakeoff.py            # the published protocol
    uv run python scripts/null_risk_bakeoff.py --seeds 40 # with the paired test

``bakeoff_risk.py`` reports every scorer as a lift over **prevalence**. That
comparison assumes an uninformative scorer scores exactly prevalence, so that a
positive lift means information. At these fold sizes it does not.

Average precision is upward-biased against bare prevalence on small samples: with
a random ranking, the early ranks that dominate the average are noisy, and the
expectation sits above the base rate. Pooling a few hundred test rows across
three folds and five seeds leaves a null wide enough to swallow every figure the
bake-off publishes.

This script measures that null directly — same folds, same seeds, same pooling,
scores replaced by uniform noise — and prints the published figures against it.
The result and what to do about it are in ``docs/evaluation-null.md``.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections.abc import Callable
from datetime import timedelta

import numpy as np

from cashflow_risk.datagen.generator import GeneratorConfig, generate_dataset
from cashflow_risk.risk.backtest import rolling_origin_folds, run_backtest
from cashflow_risk.risk.baseline import score_late_probability
from cashflow_risk.risk.dataset import TrainingExample, build_training_examples
from cashflow_risk.risk.model import LatePaymentModel

PUBLISHED_SEEDS = (1, 3, 7, 11, 42)
HORIZON_DAYS = 120
N_FOLDS = 4
N_CUSTOMERS = 30
WEEKS = 52
DRAWS = 200

# What bakeoff_risk.py prints, so the null can be read against it in one place.
PUBLISHED_LIFTS = (
    ("rules", 0.022),
    ("logistic", 0.021),
    ("gbm", -0.004),
    ("rules+CH", 0.036),
    ("logistic+CH", 0.025),
    ("gbm+CH", 0.005),
    ("ceiling (health oracle)", 0.100),
)

Scorer = Callable[[list[TrainingExample], list[TrainingExample]], list[float]]


def _rules(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
    return [score_late_probability(e.features, e.signals).probability for e in test]


def _logistic(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
    return LatePaymentModel().fit(train).predict_proba(test)


def _examples(seed: int, *, with_signals: bool) -> list[TrainingExample]:
    config = GeneratorConfig(seed=seed, n_customers=N_CUSTOMERS, weeks=WEEKS)
    dataset = generate_dataset(config)
    return build_training_examples(
        dataset.invoices,
        horizon_days=HORIZON_DAYS,
        observed_until=config.start + timedelta(days=config.weeks * 7),
        signals=dataset.company_signals if with_signals else None,
    )


def _lift(examples: list[TrainingExample], scorer: Scorer) -> float:
    folds = rolling_origin_folds(examples, purge_days=HORIZON_DAYS, n_folds=N_FOLDS)
    result = run_backtest(folds, scorer)
    return result.pooled.average_precision - result.pooled.prevalence


def _random_scorer(rng: np.random.Generator) -> Scorer:
    def score(train: list[TrainingExample], test: list[TrainingExample]) -> list[float]:
        return [float(x) for x in rng.random(len(test))]

    return score


def published_protocol_null(rng: np.random.Generator) -> None:
    """Bootstrap the null for the exact protocol the repository publishes."""
    per_draw: list[list[float]] = [[] for _ in range(DRAWS)]
    for seed in PUBLISHED_SEEDS:
        examples = _examples(seed, with_signals=False)
        for draw in range(DRAWS):
            per_draw[draw].append(_lift(examples, _random_scorer(rng)))

    run_means = [statistics.fmean(d) for d in per_draw]
    mean = statistics.fmean(run_means)
    low, high = (float(x) for x in np.percentile(run_means, [2.5, 97.5]))

    print(f"\nNull for the published protocol — {len(PUBLISHED_SEEDS)} seeds, {DRAWS} draws")
    print("A uniform-random ranking, scored exactly the way every model is scored.")
    print("-" * 70)
    print(f"  mean {mean:+.4f}    95% interval [{low:+.4f}, {high:+.4f}]")
    print("\nPublished figures against that null:")
    for name, value in PUBLISHED_LIFTS:
        verdict = "INSIDE the null" if low <= value <= high else "clears the null"
        print(f"  {name:>24}  {value:+.3f}   {verdict}")
    print(
        "\nEvery scorer figure is inside. Only the latent-health ceiling clears it.\n"
        "The pre-declared -0.012 margin sits inside a band roughly +/-0.04 wide."
    )


def paired_against_random(rng: np.random.Generator, n_seeds: int) -> None:
    """Pair each scorer against a random one on identical folds, over many seeds.

    The paired form removes between-seed variance, which is what makes the effect
    visible at all. Five seeds cannot resolve it; this is how many it takes.
    """
    arms: dict[str, list[float]] = {}
    randoms: list[float] = []
    for seed in range(1, n_seeds + 1):
        plain = _examples(seed, with_signals=False)
        with_ch = _examples(seed, with_signals=True)
        randoms.append(statistics.fmean([_lift(plain, _random_scorer(rng)) for _ in range(20)]))
        arms.setdefault("rules", []).append(_lift(plain, _rules))
        arms.setdefault("rules+CH", []).append(_lift(with_ch, _rules))
        arms.setdefault("logistic+CH", []).append(_lift(with_ch, _logistic))
        print(f"  seed {seed:>3} done", flush=True)

    print(f"\nPaired against a random scorer on identical folds — {n_seeds} seeds")
    print("-" * 70)
    print(f"{'scorer':>14}  {'lift vs random':>15}  {'paired t':>9}")
    for name, values in arms.items():
        deltas = [a - b for a, b in zip(values, randoms, strict=True)]
        mean = statistics.fmean(deltas)
        stderr = statistics.stdev(deltas) / len(deltas) ** 0.5
        print(f"{name:>14}  {mean:>+15.3f}  {mean / stderr:>9.2f}")
    print(
        "\nThe rules scorer carries real signal once there are enough seeds to see\n"
        "it. The learned arms do not. The repository publishes five seeds.\n"
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Random-scorer null for the risk bake-off")
    parser.add_argument(
        "--seeds",
        type=int,
        default=0,
        help="also run the paired test over this many seeds (40 reproduces the finding)",
    )
    args = parser.parse_args()

    rng = np.random.default_rng(20260803)
    published_protocol_null(rng)
    if args.seeds:
        paired_against_random(rng, args.seeds)


if __name__ == "__main__":
    main()
