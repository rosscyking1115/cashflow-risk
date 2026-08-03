# Changelog

Corrections are recorded here as corrections, not as tidy-ups. A visible
retraction reads as trustworthy; a silent edit reads as nothing at all, until
somebody finds the diff.

## Unreleased

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
