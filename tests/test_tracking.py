"""MLflow tracking of backtest results — against a local file store, no server.

Training-time only (PLAN §0.1): mlflow-skinny lives in the `train` dependency
group, is imported only by scripts and these tests, and never ships in the SaaS
runtime image.
"""

from pathlib import Path

import pytest
from mlflow.tracking import MlflowClient

from cashflow_risk.risk.backtest import BacktestResult
from cashflow_risk.risk.evaluation import RiskEvaluation
from cashflow_risk.risk.tracking import log_backtest


def _eval(ap: float, prev: float = 0.3, n: int = 100) -> RiskEvaluation:
    return RiskEvaluation(
        n=n,
        prevalence=prev,
        average_precision=ap,
        top_decile_precision=0.5,
        calibration_error=0.12,
        brier=0.2,
    )


def _sqlite_uri(tmp_path: Path) -> str:
    # MLflow 3.x deprecates the filesystem store; a SQLite file is the
    # serverless backend of choice (and *.db is already gitignored).
    return f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"


def test_log_backtest_records_params_pooled_metrics_and_per_fold_history(
    tmp_path: Path,
) -> None:
    uri = _sqlite_uri(tmp_path)
    result = BacktestResult(
        n_folds=2,
        pooled=_eval(0.42),
        per_fold=[_eval(0.40, n=50), _eval(0.44, n=50)],
        cold_start=_eval(0.35, n=20),
    )

    run_id = log_backtest(
        result,
        run_name="logistic+CH",
        params={"seed": 7, "horizon_days": 120, "model": "logistic+CH"},
        tracking_uri=uri,
        experiment="risk-bakeoff",
    )

    client = MlflowClient(tracking_uri=uri)
    run = client.get_run(run_id)

    assert run.info.run_name == "logistic+CH"
    assert run.data.params["seed"] == "7"
    assert run.data.params["horizon_days"] == "120"

    m = run.data.metrics
    assert m["pooled_average_precision"] == 0.42
    assert m["pooled_prevalence"] == 0.3
    assert m["pooled_lift"] == pytest.approx(0.12)
    assert m["pooled_top_decile_precision"] == 0.5
    assert m["pooled_calibration_error"] == 0.12
    assert m["pooled_brier"] == 0.2
    assert m["cold_start_average_precision"] == 0.35
    assert m["n_folds"] == 2

    history = client.get_metric_history(run_id, "fold_average_precision")
    assert [h.value for h in sorted(history, key=lambda h: h.step)] == [0.40, 0.44]


def test_runtime_api_never_imports_train_only_packages() -> None:
    """The runtime image installs with --no-dev, so the train group (mlflow,
    lightgbm) isn't there. Guard the invariant at import level: loading the API
    must not pull either in (checked in a fresh interpreter so this test file's
    own imports don't pollute the check)."""
    import subprocess
    import sys

    code = (
        "import sys; import cashflow_risk.api; "
        "bad = [m for m in sys.modules if m.split('.')[0] in ('mlflow', 'lightgbm')]; "
        "assert not bad, f'runtime API transitively imports train-only packages: {bad}'"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_runs_accumulate_in_the_same_experiment(tmp_path: Path) -> None:
    uri = _sqlite_uri(tmp_path)
    result = BacktestResult(
        n_folds=1, pooled=_eval(0.4), per_fold=[_eval(0.4)], cold_start=_eval(0.3)
    )

    a = log_backtest(result, run_name="rules", params={}, tracking_uri=uri, experiment="exp")
    b = log_backtest(result, run_name="logistic", params={}, tracking_uri=uri, experiment="exp")

    client = MlflowClient(tracking_uri=uri)
    exp = client.get_experiment_by_name("exp")
    assert exp is not None
    runs = client.search_runs([exp.experiment_id])
    assert {r.info.run_id for r in runs} == {a, b}
