"""Evaluation metrics for the late-payment risk model (PLAN §7).

PR-AUC vs the prevalence baseline, top-decile precision tied to a realistic chase
capacity, and calibration error. Hand-checked against known values so the harness
itself is trustworthy before it judges any model.
"""

import math

from cashflow_risk.risk.evaluation import (
    average_precision,
    brier_score,
    evaluate,
    expected_calibration_error,
    prevalence,
    top_k_precision,
)


def test_prevalence_is_positive_rate() -> None:
    assert prevalence([1, 0, 1, 0, 0]) == 0.4
    assert prevalence([0, 0, 0]) == 0.0


def test_average_precision_perfect_ranking_is_one() -> None:
    y = [1, 1, 0, 0]
    scores = [0.9, 0.8, 0.2, 0.1]
    assert average_precision(y, scores) == 1.0


def test_average_precision_known_interleaved_value() -> None:
    # ranking: pos, neg, pos, neg -> AP = (1/1 + 2/3) / 2 = 5/6
    y = [1, 0, 1, 0]
    scores = [0.9, 0.8, 0.7, 0.6]
    assert math.isclose(average_precision(y, scores), 5 / 6)


def test_average_precision_of_random_scores_is_near_prevalence() -> None:
    import numpy as np

    rng = np.random.default_rng(0)
    y = [int(v) for v in rng.integers(0, 2, size=2000)]
    scores = [float(v) for v in rng.random(2000)]  # scores independent of labels
    assert math.isclose(average_precision(y, scores), prevalence(y), abs_tol=0.03)


def test_top_k_precision_counts_positives_in_the_top_k() -> None:
    y = [1, 0, 1, 0, 0]
    scores = [0.9, 0.8, 0.7, 0.2, 0.1]
    assert top_k_precision(y, scores, k=2) == 0.5  # top two = {0.9(pos), 0.8(neg)}
    assert top_k_precision(y, scores, k=3) == 2 / 3


def test_brier_and_ece_reward_calibration() -> None:
    y = [1, 0, 1, 0]
    good = [0.9, 0.1, 0.8, 0.2]
    bad = [0.1, 0.9, 0.2, 0.8]
    assert brier_score(y, good) < brier_score(y, bad)
    assert 0.0 <= expected_calibration_error(y, good) <= 1.0
    # perfectly confident-and-correct -> zero Brier
    assert brier_score([1, 0], [1.0, 0.0]) == 0.0


def test_evaluate_bundles_the_metrics() -> None:
    report = evaluate([1, 0, 1, 0], [0.9, 0.2, 0.7, 0.1], chase_capacity=2)
    assert report.prevalence == 0.5
    assert report.average_precision == 1.0
    assert report.top_decile_precision == 1.0  # k=chase_capacity=2, both top are positive
    assert 0.0 <= report.calibration_error <= 1.0
    assert report.n == 4
