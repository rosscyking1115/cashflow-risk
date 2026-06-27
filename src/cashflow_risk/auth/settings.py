"""Auth configuration, read from the environment at call time.

Defaults are **secure**: dev token minting is off unless explicitly enabled, so a
deployment that forgets to configure anything cannot mint tenant tokens.
"""

from __future__ import annotations

import os

# Dev fallback only. Production MUST set CASHFLOW_JWT_SECRET (and ideally move to
# an asymmetric IdP key — see tokens.verify_token).
_DEV_SECRET = "dev-insecure-secret-set-CASHFLOW_JWT_SECRET-in-prod"


def jwt_secret() -> str:
    return os.environ.get("CASHFLOW_JWT_SECRET", _DEV_SECRET)


def dev_token_enabled() -> bool:
    """Whether the local-only /api/auth/dev-token endpoint is exposed."""
    if os.environ.get("CASHFLOW_ENV", "").lower() == "dev":
        return True
    return os.environ.get("CASHFLOW_ALLOW_DEV_TOKEN", "").lower() in ("1", "true", "yes")


def is_production() -> bool:
    return os.environ.get("CASHFLOW_ENV", "").lower() not in ("", "dev", "test", "local")


def using_default_secret() -> bool:
    return jwt_secret() == _DEV_SECRET
