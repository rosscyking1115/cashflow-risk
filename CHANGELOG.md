# Changelog

Corrections are recorded here as corrections, not as tidy-ups. A visible
retraction reads as trustworthy; a silent edit reads as nothing at all, until
somebody finds the diff.

## Unreleased

### Removed — the dashboard screenshot asserted a corrected-away framing

`docs/images/dashboard.png` was committed before seven subsequent changes to
`web/`, three of which changed exactly what a reader would look at it for. The
image lacked the **"Synthetic demo data"** banner, lacked the note that risk
scores are **not calibrated probabilities**, and labelled each row **"39% late"**
where the application now says **"risk 39%"** with a tooltip stating it is a
ranking score.

So the README's own honesty block said every figure comes from a seeded
generator, directly above the one version of the dashboard that did not say so,
still presenting the probability framing this project has published a correction
against. Verified by running the current dashboard and comparing.

Removed rather than left in place. A missing image is honest; that one was not. A
replacement is pending.

### Corrected — the bake-off had no null distribution

Every scorer in `scripts/bakeoff_risk.py` is reported as a lift over
**prevalence**, and that comparison assumes an uninformative scorer scores exactly
prevalence. At these fold sizes it does not: average precision is upward-biased
against bare prevalence on small samples, and a uniform-random ranking scores
**+0.0212** on the published protocol, 95% interval **[−0.0149, +0.0613]**.

**Every scorer figure the project publishes is inside that interval** — rules
+0.022, logistic +0.021, gbm −0.004, rules+CH +0.036, logistic+CH +0.025, gbm+CH
+0.005. Only the health-oracle ceiling at +0.100 clears it. The pre-declared
−0.012 margin was being read as a meaningful negative inside a band roughly ±0.04
wide.

The same measurement also found the project had been **understating** its one real
result. Paired against a random scorer on identical folds over 40 seeds, rules+CH
is **+0.032 (t = 3.31)** and rules is **+0.019 (t = 2.36)**, while logistic+CH is
+0.003 (t = 0.30). The rules scorer carries signal; the learned arms do not. Five
seeds cannot resolve either half, and five seeds is what is published.

The defect class is **a comparison with no null distribution**. The baseline was
derived from the label distribution when it should have been the same protocol run
with the scores replaced by noise.

Unaffected, and worth saying because it is the substance of the project: the purge
findings. Those are paired within-seed comparisons on identical test windows with a
control that cannot move, which is the right design. The calibration measurements
are likewise unaffected.

Full account in [docs/evaluation-null.md](docs/evaluation-null.md). Reproduced by
`scripts/null_risk_bakeoff.py` and `scripts/controls_risk_generator.py`, both added
in this change — a finding whose evidence lives outside the repository is not a
finding.

`bakeoff_risk.py` itself is **not** changed. It still reports lifts over prevalence
on five seeds. Folding the null into its output and raising the seed count is
outstanding work.

### Checked — the benchmark is not circular

Recorded because it was the suspicion that started the audit. The generator drives
lateness from latent customer health and a latent macro factor, and the model sees
neither. Scoring the folds with the generator's own drivers gives +0.309 (`p_late`),
+0.247 (`macro`) and +0.100 (`customer_health`) against the best shipped scorer's
+0.036 — so the models are not recovering the construction. Severing lateness from
every latent variable collapses every arm. `scripts/controls_risk_generator.py`.

### Corrected — synthetic customers named real companies

The synthetic data generator assigned company numbers `10000000`–`10000029` and
attached fabricated Companies House signals to them — `has_insolvency`,
`accounts_overdue`, `confirmation_overdue`, `has_charges`, each an independent
random draw.

**Those are real, currently-registered UK companies.** Checked on the public
register: `10000001` is WILBCO 1 LIMITED (status *Liquidation*) and `10000015` is
CLAYDONS NEWSAGENTS LTD (status *Active — proposal to strike off*). The block was
issued around February 2016 and is densely populated.

So a public repository was publishing invented distress flags under identifiers
that name real firms, with nothing anywhere saying the numbers were meant to be
fictional. That the first one checked is genuinely in liquidation makes it worse
rather than better: it makes fabrication look like a lookup.

Identifiers are now `SYNTH-0000`, `SYNTH-0001`, … A Companies House number is
exactly eight alphanumeric characters — eight digits, or a two-letter prefix and
six digits. The new format is ten characters and contains a hyphen, so it fails
on **shape**, not on a range that happens to be unissued today. Ranges get
issued; shapes do not change. `SYNTH-0000`, `SYNTH-0001` and `SYNTH-0015` were
each taken to the public register and each returns nothing.

**No published figure changed.** The identifier is inert — it is stored on the
signal record and never enters a random draw or a feature — so every bake-off
number is bit-identical before and after. This was a correctness and
public-conduct fix, not a numerical one.

Not covered by this change: several test fixtures use short real-format numbers
(`00000001`, `12345678`) and attach invented signals to them in the same way, at
much smaller scale and in no published figure.
