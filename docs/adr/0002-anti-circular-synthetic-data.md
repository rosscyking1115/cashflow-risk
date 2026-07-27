# Synthetic data generator must hide its mechanism from the model

Training and evaluating the late-payment risk model on data we generated
ourselves is circular: the model would recover the rules we injected, and
"beats baselines" would prove nothing. We decided the generator produces payment
behaviour from a **latent mechanism the model is never given** — per-Customer
latent payment health (persistent) and a shared macro factor (AR(1)).
Synthetic-data metrics are treated as **pipeline unit-tests of engine
correctness**, never as evidence of predictive skill. Predictive claims are valid
only on held-out real data.

> **Correction (27 Jul 2026).** This record previously stated that the generator's
> delay and late-rate distributions were *anchored to real GOV.UK Payment
> Practices Reporting data*. That was never true. The distributions are
> hand-chosen parameters — `beta(2, 2)` health, a fixed logit, a lognormal delay —
> with no published source behind them and no code comparing them to one.
> Anchoring them to a real reference remains a sensible thing to do; it has not
> been done, and until it is, no magnitude from this generator may be described as
> calibrated. See [CREDIBILITY.md](../CREDIBILITY.md).

## Consequences

- The model's feature set must exclude the latent health and macro factor; it may
  only use observable history (ageing, terms, amount, prior payment behaviour),
  computed as-of ≤ the prediction time.
- A future engineer must NOT "improve" the model by feeding it generator
  parameters — that would re-introduce the circularity this decision exists to
  prevent.
- `days_overdue` and the eventual payment date are labels, never features.
