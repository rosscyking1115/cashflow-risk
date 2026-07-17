# Security

An invoice ledger is commercially sensitive, and where the customers are sole
traders it is personal data too, so security and privacy were build constraints
here rather than a later pass. This page is the short version. The detail is in
[docs/threat-model.md](docs/threat-model.md),
[docs/security_privacy.md](docs/security_privacy.md) and
[docs/dpia.md](docs/dpia.md).

## Reporting a vulnerability

Please report suspected vulnerabilities privately rather than opening a public
issue. Email **rosscyking@gmail.com** with steps to reproduce and the impact you
saw. I aim to acknowledge within 3 working days and to agree a disclosure timeline
with you. Good-faith security research is welcome; please don't access other
tenants' data or degrade the service.

## What's in place

Several of these are enforced by tests, so they fail the build if they regress.

- Bearer-JWT auth, verified against Clerk's JWKS (RS256) in production. Every
  query is scoped by `business_id`, owners and invited accountants hold separate
  roles, and a test asserts that one tenant cannot read another's run. The
  dev-token endpoint stays off unless explicitly enabled, and the API refuses to
  boot in production on the default secret.
- Raw uploads are never stored. Only derived analysis results are.
- Sentry runs with no PII, no local variables, no request bodies, and
  `before_send` redaction. A test uploads marker values and checks that no
  financial field reaches the logs.
- Exports escape cells beginning with `=`, `+`, `-` or `@`, so a spreadsheet
  cannot execute them.
- Uploads have a streamed size limit and a row limit and are content-sniffed.
  Excel and binary files are rejected with a message saying what to send instead.
- The audit log is append-only and tenant-scoped, covering imports, exports and
  membership changes.
- Data rights: self-serve export and delete, and a 24-month retention purge.

## Continuous checks

Every push and pull request runs `ruff`, `mypy --strict`, `pytest` (including the
tests above), a check that the migrations apply to an empty database and still
match the models, and the web build. See
[.github/workflows/ci.yml](.github/workflows/ci.yml).

## Supported versions

One continuously deployed service, so only the tip of `main` is supported. There
are no released versions to back-port fixes to.
