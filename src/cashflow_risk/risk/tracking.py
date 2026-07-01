"""MLflow tracking for risk-model backtests (PLAN §0.1: tracking-only).

Training-time code: ``mlflow-skinny`` lives in the ``train`` dependency group,
so this module is importable in dev and on a training box but **never in the
SaaS runtime image** (the Docker build installs with ``--no-dev``). Nothing under
``cashflow_risk.api`` may import it.

One :func:`log_backtest` call = one MLflow run: the scorer's params, the pooled
metric bundle, the cold-start slice, and per-fold average precision as a step
series — enough to audit the rules → logistic → (maybe) LightGBM progression
without a server (the default store is a local ``mlruns/`` directory).
"""

from __future__ import annotations

from collections.abc import Mapping

import mlflow

from cashflow_risk.risk.backtest import BacktestResult


def log_backtest(
    result: BacktestResult,
    *,
    run_name: str,
    params: Mapping[str, object],
    tracking_uri: str,
    experiment: str = "risk-bakeoff",
) -> str:
    """Log one backtest as one MLflow run; returns the run id.

    ``params`` should carry everything needed to reproduce the run (model
    variant, seed, horizon, fold count, generator config...).
    """
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name=run_name) as run:
        if params:
            mlflow.log_params({k: str(v) for k, v in params.items()})
        pooled = result.pooled
        mlflow.log_metrics(
            {
                "n_folds": float(result.n_folds),
                "pooled_n": float(pooled.n),
                "pooled_prevalence": pooled.prevalence,
                "pooled_average_precision": pooled.average_precision,
                "pooled_lift": pooled.average_precision - pooled.prevalence,
                "pooled_top_decile_precision": pooled.top_decile_precision,
                "pooled_calibration_error": pooled.calibration_error,
                "pooled_brier": pooled.brier,
                "cold_start_n": float(result.cold_start.n),
                "cold_start_average_precision": result.cold_start.average_precision,
            }
        )
        for step, fold in enumerate(result.per_fold):
            mlflow.log_metrics(
                {
                    "fold_average_precision": fold.average_precision,
                    "fold_prevalence": fold.prevalence,
                },
                step=step,
            )
        return str(run.info.run_id)
