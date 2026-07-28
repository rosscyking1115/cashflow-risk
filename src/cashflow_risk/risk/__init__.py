"""Late-payment risk scoring. Rules baseline before any ML.

The scores are **ranking scores, not calibrated probabilities**. They are emitted
on a 0–1 scale and read like probabilities, but on the synthetic data the shipped
scorer has a mean expected calibration error of 0.186 — 0.212 once Companies House
signals are in, and the runtime uses those whenever ``COMPANIES_HOUSE_API_KEY`` is
set — and over-predicts lateness by 17 to 20 percentage points (mean predicted
0.46 to 0.49 against a prevalence of 0.29).

Use them to order invoices by which to chase first, which is what the product does
with them. Do not read "60%" as "this invoice is 60% likely to be late". See
``docs/model-evaluation.md``.
"""
