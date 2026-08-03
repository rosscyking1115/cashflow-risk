# Model evaluation — an honest read on late-payment risk

> How the late-payment risk model is measured: leakage-safe features, a purged
> rolling-origin group-aware backtest, and metrics that match the decision being
> made. It reports where the model beats its baseline and where it does not. Every
> number here is on synthetic data and is a pipeline check, not a predictive claim
> (see [adr/0002](adr/0002-anti-circular-synthetic-data.md) and
> [CREDIBILITY.md](CREDIBILITY.md)).

> [!IMPORTANT]
> **Correction — this page's comparisons had no null distribution.** Every scorer
> figure below is reported as a lift over *prevalence*, and at these fold sizes an
> uninformative scorer already scores **+0.0212** on that scale. All of them are
> inside the resulting null; only the health-oracle ceiling clears it. Measured
> properly — paired against a random scorer over 40 seeds — the rules scorer does
> carry signal (**rules+CH +0.032, t = 3.31**) and the fitted rungs do not. The
> figures below are accurate measurements and have not been altered; what they
> support is narrower than this page said.
> **Read [evaluation-null.md](evaluation-null.md) before any number here.**

## Summary

At the issue-time prediction origin, **neither fitted rung beats its rules
counterpart**. Logistic regression and gradient boosting both land on or below it
once the folds
are purged of training rows whose labels had not yet resolved. A diagnostic health
oracle, which reads the generator's own latent truth, clears prevalence by only
0.100 mean PR-AUC lift, so the ceiling is low before any model starts. What is
left is a macro factor you cannot observe at issue time without leaking the label.

An earlier version of this page reported a visible edge for the fitted models
(logistic +0.044 against rules +0.008, on the original all-four-unpurged-folds
protocol). That gap was look-ahead, not skill. See
[Purging the label horizon](#purging-the-label-horizon).

## The prediction problem

Predict, **at the moment an invoice is issued**, whether it will be paid late.
Issue-time is the hard, honest origin: you know the customer's history and the
invoice terms, but nothing about how *this* invoice ages — so the strongest naive
signal (`days_overdue_now`) is identically zero and carries nothing.

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

- **Rolling-origin (walk-forward) backtest** — expanding-window temporal folds,
  ordered by prediction origin. No fold is scored on a period its training window
  has already seen.
- **Purged by the label horizon** — a training row is dropped unless its label had
  already resolved when the test window opened. Without this, a row issued shortly
  before the boundary carries an outcome from inside the test period. This is the
  correction described below, and it is the difference between the two arms in
  every table on this page.
- **Group-aware / cold-start slice** — test customers unseen in training are
  measured separately (generalisation to new customers, where there's no history).
- **Observability of the label** — examples whose horizon falls past the data's
  censoring point are dropped, so a not-yet-resolved invoice is never miscounted as
  a "still unpaid" positive.
- **Metrics matched to a rare, ranked problem** — not accuracy:
  **PR-AUC vs the prevalence baseline** (the base rate a coin-flip scores),
  **top-decile precision** tied to a realistic chase capacity, and **calibration**
  (Brier + expected calibration error). Reported pooled and per fold.

## Purging the label horizon

The backtest originally split folds on the invoice's **issue date** alone. But an
example's label does not resolve at its origin — it resolves 120 days later. A
training row issued a week before the test window therefore carried an outcome
from *inside* that window: information nobody would have had on the day the model
would really have been fitted.

Measured on this data, **69.7% of training rows across the surviving windows**
(3,552 → 1,076) had a label that closed at or after the test window opened. The
earliest fold was separately 100% overlapping — it has no legitimately trainable
history at all, so purging drops it entirely, leaving 3 usable folds of 4 on every
seed. Counting that dropped fold's rows as "purged" as well gives 74.5%, which is
a different measurement; the like-for-like figure is 69.7% and it is what
`scripts/bakeoff_risk.py` prints.

`rolling_origin_folds(..., purge_days=120)` now removes those rows. Both arms below
run on the **same test windows**, so the difference is the overlap and nothing
else:

| scorer | purged (correct) | unpurged | what the overlap was worth |
|---|---|---|---|
| rules | +0.022 | +0.022 | +0.000 |
| logistic | +0.021 | +0.048 | +0.028 |
| gbm | −0.004 | +0.036 | +0.041 |
| rules + Companies House | +0.036 | +0.036 | +0.000 |
| logistic + Companies House | +0.025 | +0.039 | +0.015 |
| gbm + Companies House | +0.005 | +0.028 | +0.023 |
| **health-oracle ceiling** | **+0.100** | — | — |

Mean pooled PR-AUC lift over prevalence, 5 seeds, 3 folds each.

The **rules rows are the control**: the rules scorer ignores its training set
entirely, so purging cannot move it, and it does not — exactly +0.000 on both
variants. That is what makes the other rows readable. Every fitted model lost
ground, gradient boosting most of all, and it fell below prevalence once the
overlap was removed.

Pre-declared margin — the best fitted rung (logistic + Companies House) must beat
**rules + Companies House**, its like-for-like counterpart, by ≥0.10 pooled lift:
**not met**, margin **−0.012**. Negative, so the best fitted rung is worse than
the baseline it was meant to beat, not merely short of the bar.

Two things worth stating precisely, because they are easy to garble:

- The comparison is **within a feature variant**. Logistic+CH (+0.025) is measured
  against rules+CH (+0.036), not against plain rules (+0.022). Neither fitted rung
  beats its own rules counterpart.
- **The margin's "before" is not from this table.** The +0.020 the project used to
  publish came from the *original* protocol — all four unpurged folds. On matched
  windows the unpurged margin is **+0.003**, so the like-for-like move is
  +0.003 → −0.012. Both numbers are real; they measure different things, and
  quoting "+0.020 → −0.012" as if it came from one protocol would repeat exactly
  the mistake the matched-window design exists to prevent.

Two caveats on these numbers. Purging costs training data — the surviving folds
train on tens of rows rather than hundreds — so part of the drop is small-sample,
not leak removal alone. And per-seed spread is wide (purged logistic runs from
−0.083 to +0.211 across seeds). The purged column is the pessimistic bound and the
unpurged column is the optimistic one; the truth for a real ledger, which would be
long enough to purge without starving the model, sits between them. What the table
does establish is that the fitted models' apparent edge did not survive contact
with a correct protocol.

## The anti-circular synthetic generator

The data is generated from a **latent mechanism the model never sees**
([adr/0002](adr/0002-anti-circular-synthetic-data.md)): a persistent per-customer
*payment health*, a shared *macro factor* (AR(1), so late payments cluster in
time), heavy-tailed delays, customer concentration, and censoring. The latent truth
lives in a separate table used only for diagnostics. This is what makes the
evaluation non-circular — the model must recover signal from *observable* features,
not from the generative parameters.

## Results

**Rules baseline vs prevalence** (issue-time, 120-day horizon, single-shot — no
folds, so unaffected by the purge; `scripts/eval_risk_baseline.py`):

| seed | n | prevalence | PR-AUC | lift |
|---|---|---|---|---|
| 1 | 331 | 0.302 | 0.263 | −0.039 |
| 3 | 351 | 0.373 | 0.353 | −0.020 |
| 7 | 365 | 0.416 | 0.434 | +0.018 |
| 11 | 313 | 0.265 | 0.293 | +0.028 |
| 42 | 332 | 0.319 | 0.323 | +0.004 |

**Mean PR-AUC lift over prevalence: −0.002** — the rules baseline sits on the
prevalence line at issue time. Expected: it has only sparse customer history to go on.

**Bake-off** — the purged table above, from `scripts/bakeoff_risk.py`. Gradient
boosting did not earn its keep over logistic, and neither earned its keep over the
rules baseline. Both are retained as re-judgeable rungs for real data.

## Calibration: the scores are not calibrated, and the product says so

Separate from ranking, a probability-shaped output invites being read as odds. The
shipped scorer's are not. The runtime uses Companies House signals when
`COMPANIES_HOUSE_API_KEY` is set and plain rules when it is not, so both are
reported:

| scorer | mean ECE | mean Brier | mean predicted | prevalence |
|---|---|---|---|---|
| rules | **0.186** | 0.247 | 0.456 | 0.290 |
| rules + Companies House | **0.212** | 0.264 | 0.493 | 0.290 |

Per-seed ECE — rules: 0.144, 0.207, 0.223, 0.056, 0.301. With Companies House:
0.144, 0.245, 0.295, 0.059, 0.318.

The bias is systematic, not noise: mean predicted risk is 0.46 (0.49 with
Companies House) against a prevalence of 0.29, so the scorer over-predicts
lateness by roughly 17 to 20 percentage points on every seed.

So the 0–1 output is a **ranking score, not a probability**. It is good enough to
order a chase list, which is the only thing the product does with it. It is not
good enough to read "60%" as a six-in-ten chance, and nothing should present it
that way. The dashboard, the CSV export, the action brief and the package
docstring were all corrected to say "risk score"; calibrating the scorer properly
(isotonic or Platt, fitted on a purged fold) is unfinished work, not a claim.

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

Nothing here is a claim about real ledgers. What the harness would need in order to
register a win is observable signal that this generator does not contain: richer
customer histories, real Companies House distress signals that track actual
insolvency, and, if the origin were relaxed to score open invoices as they age,
`days_overdue`, which is strong. A real ledger would also be long enough to purge
the label horizon without starving the training set, which is the main thing
limiting the numbers above.

## Reproduce

```bash
uv run python scripts/eval_risk_baseline.py   # rules baseline vs prevalence
uv run python scripts/bakeoff_risk.py         # purged vs unpurged, all rungs, + ceiling
```

Code: label ([`risk/label.py`](../src/cashflow_risk/risk/label.py)), as-of features
([`features/store.py`](../src/cashflow_risk/features/store.py)), examples + censoring
([`risk/dataset.py`](../src/cashflow_risk/risk/dataset.py)), metrics
([`risk/evaluation.py`](../src/cashflow_risk/risk/evaluation.py)), purged backtest
([`risk/backtest.py`](../src/cashflow_risk/risk/backtest.py)), generator
([`datagen/generator.py`](../src/cashflow_risk/datagen/generator.py)).
