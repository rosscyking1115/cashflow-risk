# Security

Cashflow Risk Intelligence handles personal and commercially sensitive financial
data, so security and privacy are build-time requirements, not a later phase.
This document is the entry point; the detail lives in
[docs/threat-model.md](docs/threat-model.md),
[docs/security_privacy.md](docs/security_privacy.md), and
[docs/dpia.md](docs/dpia.md).

## Reporting a vulnerability

Please report suspected vulnerabilities privately — **do not open a public
issue**. Email the maintainer (see the repository owner's profile) with steps to
reproduce and the impact you observed. We aim to acknowledge within 3 working
days and to agree a disclosure timeline with you. Good-faith security research is
welcome; please avoid accessing other tenants' data or degrading the service.

## Security posture

Controls implemented and enforced by tests (see the linked docs for detail):

- **Authentication & tenancy.** Bearer-JWT auth (Clerk JWKS / RS256 in
  production); every query is scoped by `business_id`; role-based access (owner /
  invited accountant) with cross-tenant refusal covered by tests. Secure by
  default: the dev-token endpoint is off unless explicitly enabled, and the API
  refuses to boot in production with the default secret.
- **Data minimisation.** Raw uploads are never stored — only derived analysis
  results are persisted.
- **No sensitive data in logs or error reports.** Enforced by a test; Sentry is
  configured with no PII, no local variables, no request bodies, and `before_send`
  redaction.
- **Safe exports.** CSV-formula-injection defence (`=+-@` escaping) on every
  export.
- **Upload hardening.** Streamed size limit, row limit, and content sniffing;
  Excel/binary uploads are rejected with a clear message.
- **Auditability.** Append-only, tenant-scoped audit log of imports, exports, and
  membership changes.
- **Data rights.** Self-serve export and delete; automatic 24-month retention
  purge.

## Continuous checks

Every push and pull request runs `ruff`, `mypy --strict`, `pytest` (including the
security-invariant tests above), a migrations-apply-and-match check, and the web
build (see [.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Supported versions

This is a single continuously deployed service; only the currently deployed
version (the tip of `main`) is supported. There are no released versions to
back-port fixes to.
