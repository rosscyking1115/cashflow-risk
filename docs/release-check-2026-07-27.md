# Claims-versus-evidence audit — 27 Jul 2026

First audit of this repository. Thirteen-point checklist plus four repo-specific
questions. Every number below was measured on the day, on this machine, from a
clean run — none is copied from a badge or from a previous doc.

Environment: Windows 11, Python 3.12, uv. Commit audited at the start of round 1:
`e31c589` (main, in sync with `origin/main`, clean tree). The fixes live on branch
`audit/claims-vs-evidence-2026-07-27`.

---

## The four questions asked up front

### A. Is mypy strict real, and is it gated?

**Proof, not merely a claim.** All three levels hold:

| Level | Evidence |
| --- | --- |
| Configured | `strict = true` in [`pyproject.toml`](../pyproject.toml) — the real flag, not a hand-picked subset. |
| Passing | `uv run mypy` → `Success: no issues found in 44 source files`. |
| Gated | [`ci.yml`](../.github/workflows/ci.yml) runs `uv run mypy` as its own step with no `continue-on-error`, on every push to main and every pull request. A type error fails the job. |

Scope: `packages = ["cashflow_risk"]` with `mypy_path = "src"`, so it covers the
whole published package — all 44 source files, no `ignore_errors`, no per-module
opt-outs beyond four `ignore_missing_imports` entries for stub-less third-party
libraries. `tests/` (32 files) and `scripts/` (5 files) are outside the check.

This was the most under-sold thing in the repository: one static badge and one
line under "Testing and CI". **Fixed** — it now has its own README section stating
the config, the scope, the gate, and the exclusion.

The badge itself is a static `shields.io` URL rather than a live endpoint. It
cannot go stale in the way a test-count badge does, since it asserts a
configuration rather than a number, and that configuration is CI-enforced.

### B. What is the data, and is it synthetic?

**100% synthetic, from a seeded generator.** No real ledger, no real customer, no
real money anywhere in the repository. Everything comes from
[`datagen/generator.py`](../src/cashflow_risk/datagen/generator.py).

The README's original framing was mostly honest — an early note said the demo runs
on synthetic data — but it carried one **false claim** and rested on a second one
in an ADR. Both are fixed; see findings 1 and 2.

New [`docs/CREDIBILITY.md`](CREDIBILITY.md) sorts every figure into three piles
after the sibling project's pattern (engineering truth / method validation /
illustrative magnitude), and states plainly what the repository may not claim. The
largest honest gap, stated there and not hidden: **unlike the sibling, this
project has no real-data cross-check at all.**

### C. Is the risk model evaluated, or only implemented?

**Genuinely evaluated — and the evaluation is capable of failing, which it does.**

The headline check is not a tautology. `scripts/bakeoff_risk.py` compares scorers
against a pre-declared margin and prints `NOT MET`. What would make it fail is
therefore not hypothetical: it already fails. Both eval scripts reproduced their
documented tables exactly on first run, before any changes.

But there was a real **look-ahead defect**, and it was load-bearing. See finding 3.

### D. Is anything here claimed as advice?

Better than expected. A `DISCLAIMER` constant in
[`action_brief.py`](../src/cashflow_risk/reporting/action_brief.py) covers
accounting, tax, legal, credit and investment advice, and it is genuinely plumbed
through — API schema → `web/app/page.tsx` footer → CSV export. The action-brief
templates recommend chasing invoices and reviewing outflows; they never
characterise a customer or suggest borrowing.

Gaps found and fixed: the README never mentioned it (so a reader of the repository,
as opposed to a user of the app, saw risk scores with no such notice), and
Companies House signals were not described as what they are. Both addressed.

---

## Findings

Ordered by severity. Nine real defects; four checklist items came back clean.

### 1. README asserted a validation that does not exist — **severe**

`README.md:130` (as audited) read:

> Predictive claims are checked against real UK payment-practice benchmarks, never
> against synthetic data alone.

Present tense, asserting an ongoing check. **No such check exists.** There is no
GOV.UK data loader, no benchmark fixture, no calibration script and no test
anywhere in the repository. Searched: `payment[- ]practice`, `benchmark`, `gov.uk`
across all tracked files — the only hits were this sentence and the ADR behind it.

For a finance-adjacent project this is the worst available direction of error: it
implies the numbers have been reconciled against real-world payment behaviour when
they have not.

**Fixed** — replaced with a statement that the synthetic data is the only data, and
a pointer to `CREDIBILITY.md`.

### 2. ADR 0002 claimed a calibration that was never done — **severe**

`docs/adr/0002:8` stated the generator's delay and late-rate distributions were
*"anchored to real GOV.UK Payment Practices Reporting data"*. They are not. The
generator uses `beta(2, 2)` for latent health, a fixed logit
`0.3 − 2.5·health + 1.2·macro`, and a `lognormal(2.0, σ)` delay — hand-chosen
constants with no cited source and no code comparing them to a published figure.
This is what finding 1 was resting on.

**Fixed** — the false clause is removed and a dated correction block records what
the record used to say and why it was wrong. The ADR's actual decision (hide the
mechanism from the model) is untouched and still holds.

### 3. The rolling-origin backtest had no purge — **severe, and it changed the answer**

The sharpest finding, and exactly the item-13 pattern.

`rolling_origin_folds` split folds on the invoice **issue date** alone. But a
training example's label does not resolve at its origin — it resolves 120 days
later. A training row issued shortly before the test window therefore carried an
outcome from *inside* that window: information nobody would have had on the day
the model would really have been fitted.

Measured: **69.7% of training rows on the surviving windows (3,552 → 1,076)** had a
label that closed at or after the test window opened. The earliest fold was
separately 100% overlapping — it has no legitimately trainable history at all and
is dropped entirely. (Round 2 first published 74.5%, which counted the dropped
fold's rows as purged too. That mixes fold-dropping with row-purging; 69.7% is the
like-for-like figure and the one the script prints.)

The documentation asserted the opposite. `docs/model-evaluation.md` said *"a fold
is never trained on its own future"*, which was false as written, and
`tests/test_backtest.py` carried a comment `# never trained on the future` on a
test that only checks feature-date ordering and says nothing about labels.

The effect, measured on identical test windows so the comparison is like-for-like:

| scorer | purged | unpurged | delta |
| --- | --- | --- | --- |
| rules | +0.022 | +0.022 | **+0.000** |
| logistic | +0.021 | +0.048 | +0.028 |
| gbm | −0.004 | +0.036 | +0.041 |
| rules + CH | +0.036 | +0.036 | **+0.000** |
| logistic + CH | +0.025 | +0.039 | +0.015 |
| gbm + CH | +0.005 | +0.028 | +0.023 |
| health-oracle ceiling | +0.100 | — | — |

Mean pooled PR-AUC lift over prevalence, 5 seeds, 3 surviving folds each.

The **rules rows are the control**: that scorer ignores its training set entirely,
so purging cannot move it, and it moves exactly +0.000. That is what makes the
other deltas attributable to the overlap rather than to fold reshuffling — and it
is why my first attempt at this measurement was wrong and had to be redone, since
it compared different numbers of folds between the two arms.

**Every fitted model's apparent edge over the rules baseline was label overlap.**
Gradient boosting drops below prevalence. The pre-declared margin moves from
`+0.020` to **`−0.012`** — the best fitted rung is now *worse* than the baseline it
was supposed to beat, rather than merely failing to clear the bar by enough.

**Fixed** —
[`rolling_origin_folds(..., purge_days=N)`](../src/cashflow_risk/risk/backtest.py)
implemented, folds left with no trainable history are dropped rather than silently
trained on nothing, five tests added (one of which pins the old defect so it cannot
return quietly), the bake-off now reports both arms on matched windows, and the
README and evaluation doc both lead with the corrected conclusion.

Honest caveat, stated in the doc as well: purging costs training data, so the
surviving folds train on tens of rows rather than hundreds and part of the drop is
small-sample rather than leak removal alone. Purged is the pessimistic bound,
unpurged the optimistic one. What the table establishes is that the fitted
advantage did not survive a correct protocol — not that the purged figure is the
true skill.

**Feature-level look-ahead: none found.** The as-of store
([`features/store.py`](../src/cashflow_risk/features/store.py)) only admits
invoices where `paid_date <= as_of` into a customer's history, and excludes the
invoice being scored by id. The label module correctly treats paid-after-horizon
as unpaid-as-of-horizon. Both are sound.

### 4. DuckDB: a declared dependency with zero code — **checklist item 1**

`duckdb>=1.1` was a runtime dependency. **No tracked file imports it.**
`docs/architecture.md` described it in the present tense as an ephemeral engine
"spun up per forecast run", complete with a place in the data-flow diagram, and
ADR 0001 is named after it. None of that was ever built.

The same doc claimed **shadcn/ui and Recharts** for the frontend; `web/package.json`
has neither — the runtime dependencies are Clerk, Next, React and React-DOM, and
the charts are hand-written SVG and CSS.

**Fixed** — dependency removed and `uv.lock` regenerated (`Removed duckdb v1.5.4`),
architecture doc rewritten to describe what exists, ADR 0001 given a dated status
note recording that its DuckDB half was never implemented while its
sole-source-of-truth half stands.

### 5. Thirty tracked files referenced a document that is not published — **checklist item 5**

`docs/PLAN.md` is deliberately gitignored (commit `e31c589` untracked the internal
planning files). But 30 tracked files still cited it — `PLAN §6`, `PLAN §10`,
`Gate 3 (PLAN §8.3)`, `PLAN Phase 4` — across `src/`, `tests/`, `scripts/` and
`pyproject.toml`. `src/cashflow_risk/__init__.py` sent readers to
`docs/PLAN.md` for the roadmap, a file they cannot see.

Also leaking: `forecasting/baselines.py` said *"The data-science reviewer flagged
this"*, and `docs/architecture.md` ended with three internal agent-skill names.

**Fixed** — all removed or rewritten to say the thing directly rather than cite an
invisible section number. Residual sweep is clean.

### 6. No Open Government Licence attribution — **checklist item 7**

The repository is MIT and consumes the **Companies House Public Data API**, which
is published under the **Open Government Licence v3.0** and requires attribution.
No attribution existed anywhere.

**Fixed** — a "Data sources and licence" section in the README carrying the
required wording, and the same in the
[`companies_house.py`](../src/cashflow_risk/enrichment/companies_house.py)
docstring, which now also states that the signals are public filing facts and not
a credit assessment.

### 7. README overstated the DPIA and privacy notice — **checklist item 5**

The README listed *"a DPIA, a privacy notice"* as written-down reasoning. Both
documents are honestly self-labelled `— draft` with a status banner and unfilled
`[bracketed]` fields (`[your legal entity / name]`, `[date]`, `[link]`). The
documents were fine; the README's citation of them was not.

**Fixed** — the README now says they are drafts and why one is not yet required
(synthetic data does not trigger a DPIA). The documents themselves were left alone.

### 8. The advice notice was invisible outside the app — **question D**

The disclaimer reaches users of the dashboard, but nothing in the README told a
reader of the repository that the output is not advice.

**Fixed** — promoted into the opening `[!IMPORTANT]` block, alongside the
synthetic-data statement, and restated in `CREDIBILITY.md`.

### 9. A test comment claimed more than the test checked — **checklist item 13**

`tests/test_backtest.py` asserted feature-date ordering under the comment
`# never trained on the future`. The assertion is correct; the comment described a
guarantee the test did not provide, which is how finding 3 stayed invisible.

**Fixed** — comment corrected to say it covers origins only, with a pointer to the
new purge tests that do check labels.

---

## Checklist items that came back clean

A clean result is a result.

| # | Item | Finding |
| --- | --- | --- |
| 2 | Test counts that do not reproduce | **Clean.** No test-count badge or claim anywhere. Suite ran `153 passed` before changes, `158 passed` after (+5 purge tests). |
| 3 | Stale status lines, either direction | **Clean** in public files. The one contradiction (`AGENTS.md` calling this a micro-SaaS versus the README calling it a reference project) is confined to a gitignored file. |
| 4 | Numbers embedded where they rot | **Clean.** No numbers in CI step names or badge URLs. The mypy badge asserts a configuration, not a count. |
| 6 | Duplicate implementations of a core formula | **Clean.** One definition of `cash_at_risk` at `risk/baseline.py:97`; every other reference imports it. No divergent copy. |
| 8 | Unverifiable liveness claims | **Verified, not merely plausible.** The live demo returned `HTTP 200` in 33.0s; the README says the first load takes about 30 seconds to wake. All four external links returned 200. |
| 9 | Banned phrasing | **Clean.** No "production-grade" or equivalent anywhere in tracked files. |
| 11 | Branch state | **Clean.** `git fetch` run first; `main` and `origin/main` at 0 ahead / 0 behind, tree clean at start. Nothing pushed. |
| 12 | Committed build artefacts | **Clean.** `mlflow.db` exists locally but is gitignored (`.gitignore:17`). No `.next/`, parquet, notebooks or coverage output tracked. |
| — | Secrets | **Clean.** Only `.env.example` is tracked. The three matches for secret-shaped strings are self-labelled dev and test placeholders. |
| — | Internal path leakage | **Clean.** No `C:\dev`, `C:\Users`, username or `_pmo` strings in tracked files. |

Item 10 (under-sold work) is not a pass/fail — it produced findings A, 8 and the
observation below.

## Also under-sold

Beyond the mypy gate, three things the README undersold or omitted, now stated:

- **The evaluation reports a negative result.** A pre-declared margin that prints
  `NOT MET`, and a rules baseline that sits on the prevalence line. Publishing a
  check your own model fails is the strongest credibility signal in the repository.
- **The health-oracle ceiling.** Reading the generator's latent truth to establish
  what *any* model could extract, then showing the fitted models fall short of a
  ceiling that is itself low, is a better argument than any headline metric.
- **The purge control.** The rules scorer moving exactly +0.000 across arms is what
  makes the leak measurement trustworthy rather than suggestive.

---

## What this repository may and may not claim

**May claim, without qualification:**

- Every engineering property in Pile 1 of [CREDIBILITY.md](CREDIBILITY.md) —
  tenant isolation, no raw-upload storage, PII-free error reporting, CSV formula-
  injection escaping, upload limits and content sniffing, migrations that apply and
  match, and mypy strict across the whole engine. These are deterministic, tested,
  and CI-gated; synthetic input does not weaken them.
- That the evaluation protocol is correct and capable of returning a negative
  result, because it returns one.
- That the type discipline is enforced rather than asserted.

**May not claim:**

- **Any predictive skill on real invoice ledgers.** No model here has met real
  data. On synthetic data, once purged, no fitted model beats the rules baseline.
- **Calibration against real UK payment behaviour.** The generator's parameters are
  hand-chosen. Nothing here compares them to GOV.UK Payment Practices Reporting or
  any other published source.
- **Any real-data cross-check.** There is none. This is the repository's largest
  credibility gap and it is now stated in the README, `CREDIBILITY.md` and here.
- **Advice, of any kind.** Not accounting, tax, legal, credit or investment advice;
  not a recommendation about any company; not a credit assessment. Companies House
  signals are public filing facts used as model input.
- **Any magnitude as real-world performance** — runway figures, cash-at-risk
  amounts, PR-AUC, prevalence, top-decile precision. All are properties of the
  generator's assumptions.

---

## Round 2 — making the claims match the result (27 Jul 2026, later)

Round 1 found the leak and corrected the headline. Round 2 went back through every
surface that implies predictive skill, hardened the purge so the defect cannot
return, and found one more thing.

### New finding: the scores are not calibrated, and three surfaces said they were

`src/cashflow_risk/risk/__init__.py` claimed **"calibrated outputs"**. Measured on
purged folds, the shipped rules scorer:

| seed | ECE | Brier | prevalence | mean predicted |
|---|---|---|---|---|
| 1 | 0.144 | 0.237 | 0.309 | 0.444 |
| 3 | 0.245 | 0.284 | 0.278 | 0.524 |
| 7 | 0.295 | 0.304 | 0.317 | 0.592 |
| 11 | 0.059 | 0.229 | 0.348 | 0.405 |
| 42 | 0.318 | 0.267 | 0.200 | 0.503 |

**Mean ECE 0.212, mean Brier 0.264**, and the bias is systematic rather than
noisy — mean predicted risk 0.49 against prevalence 0.29, over-predicting lateness
by about 20 percentage points on every seed. `risk/evaluation.py` states the goal
as *"are the probabilities honest, so '70%' means 70%"*. They are not.

This had reached the product. The dashboard rendered `62% late`, the Excel export
had a column headed **Probability**, and the action brief read `(62% late)`.

**Withdrawn and corrected** — the package docstring now states the measured ECE and
says the output is a ranking score; the dashboard shows `risk 62%` with an
explanatory tooltip; the export column is **Risk score**; the action brief reads
`risk score 62%`; and the user-facing `DISCLAIMER` now says in as many words that a
score of 60% does not mean a 6-in-10 chance. `CONTEXT.md`, `docs/dpia.md` (risk R7)
and `CREDIBILITY.md` follow.

### Claim-by-claim disposition

Every model-performance claim in the repository, re-read against the purged result:

| Surface | Claim | Verdict |
|---|---|---|
| `scripts/bakeoff_risk.py:21` | "the fitted model ties or narrowly beats the rules baseline" | **Withdrawn** — missed in round 1. No fitted model beats rules; the best is worse. |
| `risk/__init__.py` | "calibrated outputs" | **Withdrawn** — measured ECE 0.212. |
| Dashboard / export / action brief | score presented as a probability | **Withdrawn** — relabelled as a ranking score in all three. |
| `README.md` intro | "probability of late payment × amount outstanding" | **Qualified** — now "risk score", with the ranking-not-odds caveat. |
| `CONTEXT.md` "Cash at risk" | "weighted by its late-payment probability" | **Qualified** — orders exposure, is not an expected value in pounds. |
| `README.md` / `model-evaluation.md` headline | "no fitted model beats the rules baseline" | **Stands** — reproduced again this round, byte-identical. |
| `model-evaluation.md` | health-oracle ceiling +0.100 | **Stands.** |
| `docs/dpia.md` R7 mitigation | "shows drivers + uncertainty" | **Qualified** — "uncertainty" overstated; now names the ranking-score framing and flags calibration as outstanding. |
| `CREDIBILITY.md` Pile 1 | engineering-truth claims | **Stand** — unaffected by any of this. |
| `adr/0002` | "never as evidence of predictive skill" | **Stands** — this ADR was right all along. |

Nothing was found that needed *strengthening*. The one claim that improved is the
framing: a harness that detected its own models had no edge is the finding worth
leading with, and the README now leads with it rather than burying it.

### The purge is no longer optional

`purge_days` is now a **required keyword argument with no default**. Both candidate
defaults are wrong: `0` silently restores the bug this argument exists to prevent,
and a hard-coded `120` would be right only for this project's horizon and would
under-purge any longer one. The horizon belongs to the caller's dataset, so the
caller states it. `purge_days=0` remains legal and is used exactly once — the
bake-off's deliberately leaky arm, so the leak can be measured.

Five tests added, on real generated data rather than fixtures:

- **The guard** — for every training row of every fold, asserts the label had
  already resolved when the test window opened. This is the assertion the harness
  never had.
- **Anti-vacuity** — asserts the *unpurged* arm still leaks. If that ever passes,
  the guard proves nothing.
- **The harness control** — the rules scorer ignores its training set, so purging
  must not move it by any amount. Asserted to `1e-12`. If it ever moves, the two
  arms are not comparable and no delta measured from them can be trusted.
- **Control discrimination** — a training-dependent scorer *must* move under the
  same setup, so the control above cannot pass by being insensitive.
- **Required-argument** — `rolling_origin_folds(examples)` raises `TypeError`.

**Mutation-checked.** Disabling the purge (`if False:`) fails 5 tests including the
guard; restoring it passes 14/14. The guard is not a test that cannot fail.

Note the control and the guard fail in *different* worlds by design: the control
still passes with the purge disabled, because both arms are then identical. It
catches a broken harness, not a missing purge. That is why both exist.

### Round 2 verification

`ruff` clean · `mypy` clean, 44 files · **163 passed** (158 + 5 new) ·
`alembic upgrade head` + `check` clean · `npm run build` clean (the dashboard
changed) · bake-off re-run after the API change: **numbers byte-identical**, so the
refactor is behaviour-preserving · CRLF churn from round 1 confirmed still
reverted, all modified files LF, diff is one-line changes where one-line changes
were made.

---

## Round 3 — independent review, and what it caught

After the PR was opened, an independent reviewer was given the corrected numbers
and asked to find what rounds 1 and 2 missed. It found seven further defects,
including two of mine that changed published figures. Recording them here because
an audit that does not audit itself is the thing this document exists to argue
against.

### The reviewer's two numeric catches, both confirmed by re-measurement

**1. The calibration table was the wrong scorer.** Round 2 published mean ECE
0.212 as *"the shipped rules scorer"*. It is not — the measurement script passed
`signals=ds.company_signals`, so it measured **rules + Companies House**. Plain
rules is **0.186**. Both are now reported, because the runtime uses CH signals when
`COMPANIES_HOUSE_API_KEY` is set and plain rules when it is not, so both genuinely
ship. The qualitative conclusion is unchanged; the attribution was wrong on nine
surfaces and is corrected on all of them.

**2. `+0.020 → −0.012` mixed two protocols.** The +0.020 came from the *original*
all-four-unpurged-folds run. The matched-window unpurged margin is **+0.003**.
Presenting +0.020 and −0.012 as a before-and-after pair, directly beneath a
matched-window table, commits precisely the error the matched-window design exists
to prevent. Now stated as +0.003 → −0.012 like-for-like, with +0.020 labelled as
the older protocol's number.

The same class of error produced the **74.5%** overlap figure, which counted the
dropped fold's rows as purged. Like-for-like it is **69.7%**.

### The other five

3. **The gate's baseline was misnamed.** `model-evaluation.md` said the margin was
   against *"rules"*; the script computes it against **rules+CH**. Against plain
   rules the best fitted rung is marginally *better*, so the sentence was false as
   written. The comparison is within a feature variant, and now says so.
4. **A surviving overclaim in `risk/model.py`** — *"this ties the rules baseline …
   the lift is expected once real Companies House distress signals join the
   features."* Round 2's own disposition table withdrew the near-identical
   sentence from `bakeoff_risk.py` and missed this one. Its second clause is also
   refuted by the CH arm that already exists: logistic+CH loses to rules+CH by
   more than logistic loses to rules.
5. **The API schema still said `probability`.** Every human-readable surface was
   relabelled; the machine-readable contract was not. The field keeps its name for
   wire compatibility but now carries an OpenAPI description stating it is a
   ranking score and what its ECE is.
6. **`architecture.md` claimed "uncertainty is always shown".** Nothing on the
   dashboard shows an interval. The High/Medium/Low band is a discretisation of
   the score. Corrected — the same wording was caught in the DPIA in round 2 and
   not swept for elsewhere.
7. **`evaluation.py` was silent where it should speak** — it defines ECE and says
   *"'70%' means 70%"* without recording that this model fails that test. It is
   the module that computes the number.

Also fixed: `gbm.py` did not mention that GBM now scores below prevalence, and the
figures the model card promised were reproducible (Brier, mean predicted, the
overlap percentage) were printed by nothing. `scripts/bakeoff_risk.py` now prints
all of them, so the claim is true rather than aspirational.

### What the reviewer confirmed

- Both eval scripts reproduce their published tables exactly.
- The purge guard **can** fail: monkeypatching `rolling_origin_folds` to ignore
  `purge_days` fails 5 of 7 purge tests, the guard reporting 683 leaking rows.
- gbm's own lift (+0.036 → −0.004) is correctly attributed everywhere; the
  conflation that existed was the protocol one above, not that one.
- No surviving claim that the data is real or benchmarked, no advice claim, no
  "production-grade" phrasing.

### Known remaining gap

The purge guard is pinned to `seed=7, n_customers=30, weeks=52`. A config change
that made purging vacuous would not be caught. Recorded rather than fixed.

## Reproduce this audit

```bash
uv run mypy                                   # 44 files, strict
uv run pytest                                 # full suite
uv run ruff check .
uv run python scripts/eval_risk_baseline.py   # rules vs prevalence
uv run python scripts/bakeoff_risk.py         # purged vs unpurged, matched windows
```

Round 1 and 2 changes were left in the working tree; they were committed to
`audit/claims-vs-evidence-2026-07-27` and published as PR #10 after Ross approved
the content and, separately, the publication.
