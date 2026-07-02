"""The gradient-boosted rung (PLAN §10: LightGBM only if it earns its keep).

Mechanics only, like the logistic tests: it must learn a present signal, be
reproducible, and handle the degenerate cases — no synthetic-win assertions
(the generator's issue-time ceiling makes those meaningless; see the bake-off).
"""

import pytest

from cashflow_risk.risk.evaluation import average_precision, prevalence
from cashflow_risk.risk.gbm import GradientBoostedModel
from tests.test_model import _ex, _separable


def test_predict_proba_is_bounded_and_deterministic() -> None:
    train = _separable()
    a = GradientBoostedModel().fit(train).predict_proba(train)
    b = GradientBoostedModel().fit(train).predict_proba(train)

    assert len(a) == len(train)
    assert all(0.0 <= p <= 1.0 for p in a)
    assert a == b  # fixed seed, single thread -> reproducible


def test_model_learns_a_present_signal() -> None:
    data = _separable()
    y = [1 if e.label else 0 for e in data]
    scores = GradientBoostedModel().fit(data).predict_proba(data)

    assert average_precision(y, scores) > prevalence(y) + 0.3


def test_single_class_training_falls_back_to_the_base_rate() -> None:
    all_late = [_ex(late_rate=0.9, label=True, cust=f"C{i}") for i in range(10)]
    model = GradientBoostedModel().fit(all_late)

    assert model.predict_proba(all_late[:3]) == [1.0, 1.0, 1.0]


def test_unfitted_model_and_empty_input() -> None:
    with pytest.raises(RuntimeError):
        GradientBoostedModel().predict_proba(_separable(2))
    with pytest.raises(ValueError):
        GradientBoostedModel().fit([])
    assert GradientBoostedModel().fit(_separable()).predict_proba([]) == []
