"""Authentication and tenant scoping.

Every real analysis is bound to the authenticated :class:`Principal`'s
``business_id`` (the tenant). See ``docs/security_privacy.md``.
"""

from cashflow_risk.auth.dependencies import require_principal
from cashflow_risk.auth.principal import Principal
from cashflow_risk.auth.tokens import AuthError, mint_token, verify_token

__all__ = ["AuthError", "Principal", "mint_token", "require_principal", "verify_token"]
