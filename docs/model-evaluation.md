# Model evaluation — an honest read on late-payment risk

> How the late-payment risk model is measured: leakage-safe features, a
> rolling-origin group-aware backtest, and metrics that match the decision being
> made. It reports where the model beats its baseline and where it does not. Every
> number here is on synthetic data and is a pipeline check, not a predictive claim
> (see [adr/0002](adr)).

## Summary

At the issue-time prediction origin, the fitted models (logistic and
gradient-boosted) tie the rules baseline, and both sit near the prevalence line.
That is what this data allows. A diagnostic health oracle, which reads the
generator's own latent truth, only clears prevalence by 0.099 mean PR-AUC lift, so
the ceiling is low before any model starts. What remains is a macro factor you
cannot observe at issue time without leaking the label.

## The prediction problem

Predict, **at the moment an invoice is issued**, whether it will be paid late
(PLAN §6). Issue-time is the hard, honest origin: you know the customer's history
and the invoice terms, but nothing about how *this* invoice ages — so the strongest
naive signal (`days_overdue_now`) is identically zero and carries nothing.

**Label** (pinned, with censoring): positive if paid more than *X* days after due,
**or** unpaid at the horizon *T*. Paid-after-horizon counts as unpaid *as-of T*, so
an outcome we could not yet have observed never leaks a "settled" label.

## Leakage-safe features

Features come from an **as-of feature store**: for each invoice, everything is
computed strictly from information available at its issue date — the customer's
*prior settled* invoices only, plus the invoice's own terms. The invoice's eventual
payment date is a label, never a feature. The same vectoriser feeds every model, so
a bake-off difference is the *model*, not the features.

## Evaluation protocol

- **Rolling-origin (walk-forward) backtest** — expanding-window temporal folds; a
  fold is never trained on its own future.
- **Group-aware / cold-start slice** — test customers unseen in training are
  measured separately (generalisation to new customers, where there's no history).
- **Observability of the label** — examples whose horizon falls past the data's
  censoring point are dropped, so a not-yet-resolved invoice is never miscounted as
  a "still unpaid" positive.
- **Metrics matched to a rare, ranked problem** — not accuracy:
  **PR-AUC vs the prevalence baseline** (the base rate a coin-flip scores),
  **top-decile precision** tied to a realistic chase capacity, and **calibration**
  (Brier + expected calibration error). Reported pooled and per fold.

## The anti-circular synthetic generator

The data is generated from a **latent mechanism the model never sees**
([adr/0002](adr)): a persistent per-customer *payment health*, a shared *macro
factor* (AR(1), so late payments cluster in time), heavy-tailed delays, customer
concentration, and censoring. The latent truth lives in a separate table used only
for diagnostics. This is what makes the evaluation non-circular — the model must
recover signal from *observable* features, not from the generative parameters.

## Results

**Rules baseline vs prevalence** (issue-time, 120-day horizon; `scripts/eval_risk_baseline.py`):

| seed | n | prevalence | PR-AUC | lift |
|---|---|---|---|---|
| 1 | 331 | 0.302 | 0.263 | −0.039 |
| 3 | 351 | 0.373 | 0.353 | −0.020 |
| 7 | 365 | 0.416 | 0.434 | +0.018 |
| 11 | 313 | 0.265 | 0.293 | +0.028 |
| 42 | 332 | 0.319 | 0.323 | +0.004 |

**Mean PR-AUC lift over prevalence: −0.002** — the rules baseline sits on the
prevalence line at issue time. Expected: it has only sparse customer history to go on.

**Bake-off** — rules → logistic → gradient-boosted, with and without Companies House
signals, over the rolling-origin folds, plus the latent health-oracle ceiling
(`scripts/bakeoff_risk.py`, mean pooled PR-AUC lift over prevalence):

| scorer | mean lift |
|---|---|
| rules | +0.008 |
| logistic | +0.044 |
| gbm | +0.016 |
| rules + Companies House | +0.013 |
| logistic + Companies House | +0.032 |
| gbm + Companies House | +0.009 |
| **health-oracle ceiling** | **+0.099** |

Pre-declared gate (best fitted rung beats rules by ≥0.10 pooled lift): **not met**
(margin +0.020). Gradient boosting **did not earn its keep** over logistic here, and
was retained only as a re-judgeable rung for real data.

## Why the ceiling is low (decomposition)

Reading the generator's latent variables directly (diagnostic only — never a
feature) explains the ceiling. The label is driven by two things:

- **Contemporaneous macro factor** — strongly predictive (PR-AUC ≈ 0.60–0.64), but
  it acts on the invoice's *issue week* and cannot be observed at issue time without
  leakage; AR(1) decay means it barely persists across a 120-day horizon.
- **Latent customer health** — persistent and estimable *in principle* (PR-AUC ≈
  0.36–0.50), but the only observable proxy (a customer's realised prior late-rate)
  is sparse and noisy: it correlates with true health only ~0.1–0.3, and 20–28% of
  examples are cold-start with no history at all.

So a *perfect* observer of health (the oracle) reaches only ~+0.10 lift, and
Companies House signals — a noisy subset of that health view — cannot exceed it. The
model isn't broken; the observable information at issue time is genuinely thin **on
this synthetic world by construction**.

## What this would mean on real data

The harness would register a win as soon as observable signal exists: richer
customer histories, real Companies House distress signals that track actual
insolvency, and, if the origin were relaxed to score open invoices as they age,
`days_overdue`, which is strong. The same setup would carry a real-data claim:
leakage-safe features, rolling-origin group-aware validation, calibration, and a
baseline that is genuinely hard to beat.

## Reproduce

```bash
uv run python scripts/eval_risk_baseline.py   # rules baseline vs prevalence
uv run python scripts/bakeoff_risk.py         # rules vs logistic vs GBM, ±CH, + ceiling
```

Code: label ([`risk/label.py`](../src/cashflow_risk/risk/label.py)), as-of features
([`features/store.py`](../src/cashflow_risk/features/store.py)), examples + censoring
([`risk/dataset.py`](../src/cashflow_risk/risk/dataset.py)), metrics
([`risk/evaluation.py`](../src/cashflow_risk/risk/evaluation.py)), backtest
([`risk/backtest.py`](../src/cashflow_risk/risk/backtest.py)), generator
([`datagen/generator.py`](../src/cashflow_risk/datagen/generator.py)).
