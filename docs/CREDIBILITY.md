# Credibility & how to read the numbers

Everything in this repository runs on **synthetic data**. There is no real invoice
ledger here, no real customer, and no real money. The generator is in
[`datagen/generator.py`](../src/cashflow_risk/datagen/generator.py) and it is
seeded end to end, so any number on this page can be reproduced from a clean
checkout with the commands at the bottom.

That raises the fair question a reviewer should ask:

> *Is anything here evidence, or is it a generator marking its own homework?*

The short answer: **every number falls into one of three piles, and they earn
trust in different ways.** Read a figure's pile before you read its value.

---

## The three piles

### Pile 1 — engineering truth (deterministic, exactly checkable)

These are binary. The code either does the thing or it does not, CI fails when it
does not, and there is no confidence interval anywhere near them. Synthetic data
does not weaken these at all — the input could be anything.

| Claim | Why it holds |
| --- | --- |
| A tenant cannot read another tenant's run | A test guesses another tenant's run id and asserts the refusal. |
| Raw uploads are never stored | Only derived results reach the database; asserted in the persistence tests. |
| Error reports carry no PII | A test uploads marker values and asserts none of them reach Sentry's payload. |
| Exports cannot execute in a spreadsheet | Cells starting `=`, `+`, `-`, `@` are escaped; tested against each. |
| Uploads are size- and row-limited and content-sniffed | Tested with oversized and mistyped payloads. |
| Migrations apply to an empty database and match the models | CI runs `alembic upgrade head` then `alembic check`. |
| The whole engine type-checks under mypy strict | CI runs `uv run mypy` as a blocking step. |
| Folds are purged of unresolved training labels | Tested directly, including a test that pins the old defect. |
| Generation is reproducible | Seeded; the same config produces the same ledger. |

### Pile 2 — method validation (recovering a known truth)

The generator embeds an answer, and the method is judged on whether it finds it.
Synthetic data makes these *stronger*, not weaker: on a real ledger you can never
check whether an estimator recovered the truth, because the truth is not observed.

| Claim | Why it holds |
| --- | --- |
| The model cannot see the generative mechanism | Latent health and the macro factor live in a separate table that no feature path reads ([adr/0002](adr/0002-anti-circular-synthetic-data.md)). |
| Features are computable at the decision time they claim | The as-of store reads only *prior settled* invoices and excludes the invoice being scored. |
| The health-oracle ceiling bounds what any health proxy could extract | Reading latent health directly scores +0.100 mean lift, so no observable proxy can beat that on these folds. |
| The purge changes the answer, and by how much | Both arms run on identical test windows; the rules control moves +0.000, which is what makes the other deltas readable. |
| The synthetic Companies House signals name no real company | Customer identifiers are `SYNTH-0007`, ten characters with a hyphen — structurally invalid as a Companies House number, so they cannot collide on shape rather than on an unissued range. They previously used real eight-digit numbers; see [CHANGELOG.md](../CHANGELOG.md). |

**Known weakness in the purge guard, recorded rather than fixed.** The test that
fails if a fold trains on an unresolved label is pinned to one configuration —
`seed=7, n_customers=30, weeks=52`. It catches the purge being removed, which is
what it was written for, and a mutation check confirms that. It would *not* catch a
change to the generator config that made purging vacuous on the pinned seed while
leaving it necessary elsewhere. Parameterising it across seeds and horizons is
outstanding work.

**Two figures that must never be paired.** The label overlap is **69.7%** and the
gate margin moved **+0.003 → −0.012**, both on matched windows. An earlier revision
published **74.5%** and **+0.020**; those come from the older all-four-unpurged-folds
protocol. Both are real numbers, and quoting either beside a matched-window figure
reintroduces the exact confound the matched-window design exists to remove.

### Pile 3 — illustrative magnitude (synthetic; not real-world performance)

These show the machinery working end to end. Their **magnitudes are properties of
the generator's assumptions**, not of UK SME payment behaviour. Never quote them as
real-world performance, and never quote them as a benchmark.

- Every PR-AUC, lift, top-decile precision, calibration error and prevalence figure
  in [model-evaluation.md](model-evaluation.md).
- Every runway, shortfall week, cash-at-risk amount and action brief on the demo
  dashboard.
- The late-payment rate the generator produces, which is a chosen parameter.
- **Every risk score shown in the product.** They are 0–1 ranking scores, not
  probabilities: mean ECE 0.186, or 0.212 with Companies House signals,
  systematically over-predicting lateness by 17–20 percentage points. A displayed
  "60%" means "chase this one before the 40% one", not "six-in-ten". The dashboard, export and action brief all say "risk
  score" for exactly this reason.

---

## What this repository may not claim

Stating this plainly because the domain invites the opposite reading:

- **No predictive-skill claim on real ledgers.** No model here has been evaluated
  against real invoice data. On the synthetic data neither fitted rung beats its
  rules counterpart once the folds are purged.
- **No claim that the scores are calibrated probabilities.** They are not; the
  measurement is in [model-evaluation.md](model-evaluation.md). Calibrating them is
  unfinished work.
- **No claim that the rules baseline itself has demonstrated skill.** It wins the
  bake-off only in the sense that nothing beat it. Single-shot at issue time it
  sits on the prevalence line (mean lift −0.002).
- **No calibration against real UK payment behaviour.** The generator's late-rate
  and delay distributions are hand-chosen parameters. They are not derived from
  GOV.UK Payment Practices Reporting or any other published source, and no code
  here compares them to one.
- **No real-data cross-check.** Unlike a sibling project in this cluster, the same
  code has not been re-run on a real public dataset. That is the single largest gap
  on this page and it is not hidden anywhere else.
- **Nothing here is advice.** Not accounting, tax, legal, credit or investment
  advice, and not a recommendation about any company. Companies House signals are
  public filing facts fed into a score; they are not a judgement about a business,
  and the output is not a credit assessment. See
  [security_privacy.md](security_privacy.md).

## What it may claim

- The engineering in Pile 1, without qualification.
- That the evaluation protocol is correct and that it is capable of returning a
  negative result — it does, three times over: the rules baseline sits on the
  prevalence line, the pre-declared margin is not met, and the calibration
  measurement says the scores are not probabilities. A harness that only ever
  confirms its author is not a harness, and this one keeps refusing to.
- That the type discipline is real and enforced, not asserted.

## Reproduce

```bash
uv run pytest                                 # the suite behind Pile 1
uv run mypy                                   # strict, whole engine
uv run python scripts/eval_risk_baseline.py   # rules baseline vs prevalence
uv run python scripts/bakeoff_risk.py         # purged vs unpurged, all rungs, + ceiling
```
