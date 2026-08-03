# The bake-off had no null distribution

This page reports a defect in this project's own headline evaluation. The risk
bake-off compares every scorer against **prevalence**, and prevalence is the wrong
baseline. Measured properly, **every scorer figure the bake-off publishes lies
inside the range an uninformative scorer produces on the same folds.**

The finding has two halves and both matter. One is unflattering and one is not.

| | |
| --- | --- |
| **Over-claimed** | Every published scorer lift is inside a null of **+0.0212, 95% interval [−0.0149, +0.0613]**. Only the latent-health ceiling clears it. The pre-declared **−0.012** margin is being read as a meaningful negative inside a band roughly ±0.04 wide. |
| **Under-claimed** | Paired against a random scorer on identical folds over 40 seeds, **rules+CH is +0.032 (t = 3.31)** and **rules is +0.019 (t = 2.36)**. The rules scorer carries real signal. The learned arms do not — logistic+CH is +0.003 (t = 0.30). |

Five seeds cannot resolve either half. This repository publishes five.

Reproduce both with [`scripts/null_risk_bakeoff.py`](../scripts/null_risk_bakeoff.py).

## The defect class: a comparison with no null distribution

`bakeoff_risk.py` prints, for each scorer, `average_precision − prevalence`, and
treats a positive value as evidence of information. That is only valid if an
uninformative scorer scores exactly prevalence.

It does not. **Average precision is upward-biased against bare prevalence at
small sample sizes.** Average precision is the mean of precision@k evaluated at
each positive's rank; the early ranks dominate that mean and are the noisiest part
of a random ranking. The expectation of the whole quantity therefore sits above
the base rate, and the gap widens as the sample shrinks. Pooling roughly 150 test
rows across three surviving folds is small enough for the gap to exceed every
effect the bake-off was trying to measure.

The correct baseline is not a number derived from the label distribution. It is
**the same protocol, run with the scores replaced by noise.**

## Finding 1: the null is +0.0212, and it swallows the table

A uniform-random ranking, scored exactly the way every model is scored — same
purged rolling-origin folds, same five seeds, same pooling — bootstrapped over 200
draws:

```
mean +0.0212    95% interval [-0.0149, +0.0613]
```

Against the published figures:

| Published figure | Lift over prevalence | Against the null |
| --- | --- | --- |
| rules | +0.022 | **inside** — it *is* the null mean, to three decimals |
| logistic | +0.021 | **inside** |
| gbm | −0.004 | **inside** |
| rules+CH | +0.036 | **inside** |
| logistic+CH | +0.025 | **inside** |
| gbm+CH | +0.005 | **inside** |
| ceiling (health oracle) | +0.100 | clears the null |

The rules figure landing exactly on the null mean is a coincidence of rounding,
but it is a useful one: **+0.022 is, to three decimal places, what this protocol
returns for ranking invoices at random.**

The consequence for the gate is direct. The pre-declared margin required the best
fitted rung to beat its rules counterpart by ≥ +0.10, and it came out at −0.012.
That number is real and it is reproducible, but it is being read as "the fitted
model is slightly worse". It is not distinguishable from "these two scorers were
compared with a ruler too coarse to tell them apart".

## Finding 2: the rules scorer does carry signal — the protocol could not show it

The same measurement run the other way is the good news, and leaving it out would
be as much of a misreport as the first half.

Pairing each scorer against a random scorer **on identical folds** removes the
between-seed variance that swamps the unpaired comparison. Over 40 seeds:

| Scorer | Lift vs random | Paired *t* |
| --- | --- | --- |
| rules+CH | **+0.032** | **3.31** |
| rules | **+0.019** | **2.36** |
| logistic+CH | +0.003 | 0.30 |

So the rules baseline is doing something. Adding the Companies House block to it
improves it further, and the improvement is the larger of the two effects. The
fitted rungs remain indistinguishable from noise, which is the same conclusion the
project already published — but now it is a measured conclusion rather than an
artefact of a baseline that was too generous to everybody equally.

**The repository has been understating its one real result and overstating five
figures that are not results at all.** Both follow from the same missing control.

## Finding 3: what this is *not* — the benchmark is not circular

The obvious suspicion, given a project that generates its own evaluation data, is
that the generator templates the answer into the question. It does not, and
[`scripts/controls_risk_generator.py`](../scripts/controls_risk_generator.py)
settles it.

**Positive control.** Score the folds using only the generator's own lateness
drivers, which no model can see:

| Scorer | Mean lift |
| --- | --- |
| oracle on `p_late` (the exact Bernoulli parameter) | +0.309 |
| oracle on `macro` alone | +0.247 |
| oracle on `customer_health` | +0.100 |
| best shipped scorer (rules+CH) | +0.036 |

The oracles beat every model several times over. If the models were recovering the
construction, they would match. They are nowhere near it — because the generator
withholds its mechanism exactly as [ADR 0002](adr/0002-anti-circular-synthetic-data.md)
requires, and because the larger of the two drivers, the contemporaneous macro
factor, has no issue-time proxy at all.

**Negative control.** Re-draw every invoice's lateness independently of every
latent variable, leaving customers, amounts, terms and dates untouched. Every arm
collapses. Nothing leaks.

The negative control is also how the null was found. It included a random scorer,
and the random scorer did not score zero either — which is what prompted measuring
the null on the shipped data.

## What this means for the published numbers

| Figure | Status |
| --- | --- |
| rules +0.022, logistic +0.021, gbm −0.004 | Inside the null. Not evidence of ranking ability. |
| rules+CH +0.036, logistic+CH +0.025, gbm+CH +0.005 | Inside the null. |
| The pre-declared margin −0.012 | Real and reproducible, but inside a ±0.04 band. Not a measured difference between the two scorers. |
| The purge deltas (+0.028, +0.041, +0.015, +0.023) | **Unaffected.** These are paired within-seed comparisons on identical test windows, which is the right design; the leak they measure is real. |
| The rules control moving +0.000 under the purge | **Unaffected**, and still the thing that makes the other deltas readable. |
| Calibration: ECE 0.186 / 0.212 | **Unaffected.** Calibration is not a ranking comparison and has no null of this kind. |
| Ceiling +0.100 | **Clears the null.** Still the honest upper bound on what any health proxy could extract. |
| rules+CH +0.032 vs random, t = 3.31 (40 seeds) | **The result.** |

The purge finding — the thing this repository is actually about — survives
completely. It was never a comparison against prevalence; it was a paired
comparison of the same scorer on the same windows with and without a leak, with a
control that could not move. That design was right, and it is why that half of the
evaluation is unaffected by a defect that consumed the other half.

## What the protocol should have been

1. **Report the null beside every figure.** A lift over prevalence means nothing
   on its own at these sample sizes. `null_risk_bakeoff.py` computes it in under a
   minute; there was never a cost reason not to.
2. **Pair against random on identical folds**, rather than subtracting a
   distributional constant. Pairing is what makes the effect visible.
3. **Use enough seeds to resolve the effect.** Five cannot. Forty can, and the
   whole bake-off runs in well under a minute, so the seed count was never a
   budget decision either — it was simply never questioned.
4. **Do not read a pre-declared margin without its interval.** A gate that
   compares two numbers needs to know how far apart they must be before the
   comparison means anything. This one did not.

## What has not been done

Recorded so the gap is explicit rather than implied.

- **`bakeoff_risk.py` has not been changed.** It still reports lifts over
  prevalence, still on five seeds, and still prints the −0.012 margin as its
  headline verdict. The null lives in a separate script beside it. Folding the
  null into the bake-off's own output, and raising its seed count, is the fix and
  it is outstanding.
- **The README and `MODEL_CARD.md` still carry the five-seed figures.** They are
  accurate as measurements and they are linked to this page, which is the
  correction. They have not been restated.
- **Nothing has been re-measured with the null as the baseline** beyond the three
  arms in the table above. `gbm` and the no-CH variants were not run at 40 seeds.
