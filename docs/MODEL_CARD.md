# Model card — late-payment risk scorer

One-page statement of what the model is, what it was measured at, and what it may
not be used for. Every figure here was measured on synthetic data with the
reproduction commands at the bottom.

## Headline

**No fitted model beats the rules baseline.** Logistic regression and gradient
boosting were both trained and backtested; once the evaluation was corrected for
look-ahead, neither earned its place, and gradient boosting scored below the base
rate. The model that ships is the transparent rules scorer.

That is a negative result, and it is the reason this card exists. The evaluation
was capable of detecting that its own models had no edge, and it did.

## What ships

| | |
|---|---|
| **Model in the runtime** | Deterministic rules scorer — a hand-specified log-odds form over as-of features, mapped to 0–1. `src/cashflow_risk/risk/baseline.py` |
| **Not in the runtime** | Logistic regression and LightGBM. They exist as bake-off rungs, run at training time, tracked in MLflow, and are never installed in the Docker image. |
| **Output** | A **ranking score** in 0–1, a band, the pounds at risk, and the drivers behind the score. |
| **Prediction origin** | The moment an invoice is issued. |
| **Label** | Paid more than *X* days after due, **or** unpaid at a 120-day horizon. |

## Intended use

Ordering a weekly chase list: which unpaid invoices to pursue first. That is the
only decision the score is fit for, and the only one the product asks of it.

## Out of scope

- **Not a credit assessment**, credit score, or input to a lending decision.
- **Not a judgement about any company or individual.** Companies House signals are
  public filing facts used as model input.
- **Not advice** — not accounting, tax, legal, credit or investment advice.
- **Not a probability.** See calibration below.
- **Not validated on real invoice data.** Nothing here has met a real ledger.

## How it was evaluated

Rolling-origin (walk-forward) backtest, expanding window, grouped so that
customers unseen in training are scored separately. Metrics are PR-AUC against
the prevalence base rate, top-decile precision at a realistic chase capacity, and
calibration (Brier + ECE), pooled and per fold.

**Purged by the label horizon.** A training row is dropped unless its outcome had
already resolved when the test window opened. This is the correction that changed
the result — see below.

## Results

Mean pooled PR-AUC lift over prevalence, 5 seeds, 3 surviving folds each. Both
arms run on **identical test windows**, so the only difference is the training
label overlap:

| scorer | purged (correct) | unpurged | difference |
|---|---|---|---|
| rules | +0.022 | +0.022 | **+0.000** ← control |
| logistic | +0.021 | +0.048 | +0.028 |
| gradient boosting | **−0.004** | +0.036 | +0.041 |
| rules + Companies House | +0.036 | +0.036 | **+0.000** ← control |
| logistic + Companies House | +0.025 | +0.039 | +0.015 |
| gbm + Companies House | +0.005 | +0.028 | +0.023 |
| **health-oracle ceiling** | **+0.100** | — | — |

Two separate numbers, easily confused, so both stated plainly:

- **Gradient boosting's own lift** went from +0.036 to **−0.004** — below
  prevalence, meaning it ranks worse than the base rate.
- **The pre-declared gate margin** — best fitted rung (logistic + Companies House)
  minus rules + Companies House, required to be ≥ +0.10 — went from **+0.020 to
  −0.012**. Negative: the best fitted rung is worse than the baseline it had to
  beat.

The **rules rows are the control.** That scorer never reads its training set, so
purging cannot move it, and it moves exactly **+0.000**. That zero is what makes
the other differences attributable to the leak rather than to coincidence or to
folds being reshuffled.

### Why the ceiling is low

An oracle reading the generator's latent customer health directly — diagnostic
only, never a feature — reaches just +0.100. The rest of the label is driven by a
contemporaneous macro factor that cannot be observed at issue time without
leaking. So the observable signal at the decision point is genuinely thin on this
synthetic world, by construction.

## Calibration: the scores are not probabilities

| seed | 1 | 3 | 7 | 11 | 42 |
|---|---|---|---|---|---|
| ECE | 0.144 | 0.245 | 0.295 | 0.059 | 0.318 |

**Mean ECE 0.212, mean Brier 0.264.** The bias is systematic, not noise: mean
predicted risk **0.49** against a prevalence of **0.29**, over-predicting lateness
by roughly 20 percentage points on every seed.

A displayed "60%" means *chase this one before the 40% one*. It does not mean a
six-in-ten chance. Calibrating the scorer (isotonic or Platt, fitted on a purged
fold) is unfinished work, not a claim.

## Training data

Entirely synthetic, from a seeded generator
([`datagen/generator.py`](../src/cashflow_risk/datagen/generator.py)). Payment
behaviour comes from a latent mechanism the model never sees — persistent
per-customer health, an AR(1) macro factor, heavy-tailed delays, customer
concentration and censoring
([ADR 0002](adr/0002-anti-circular-synthetic-data.md)).

The generator's parameters are **hand-chosen and not calibrated to any published
source**. They are not derived from GOV.UK Payment Practices Reporting or anything
else, and no code here compares them to one.

## Known limitations

1. **No real-data evaluation, and no real-data cross-check.** The largest gap.
2. **Purging costs training data.** Surviving folds train on tens of rows rather
   than hundreds, so part of the drop is small-sample rather than leak removal
   alone. The purged column is a pessimistic bound; the unpurged is optimistic.
   The truth for a real ledger, long enough to purge without starving the model,
   sits between them.
3. **Wide per-seed spread** — purged logistic ranges from −0.083 to +0.211.
4. **Uncalibrated output**, quantified above.
5. **Cold-start customers** (20–28% of examples) have no history to score from.

## Reproduce

```bash
uv run python scripts/eval_risk_baseline.py   # rules baseline vs prevalence
uv run python scripts/bakeoff_risk.py         # purged vs unpurged, matched windows
```

See [model-evaluation.md](model-evaluation.md) for the workings and
[CREDIBILITY.md](CREDIBILITY.md) for what every number in the repository may and
may not be read as.
