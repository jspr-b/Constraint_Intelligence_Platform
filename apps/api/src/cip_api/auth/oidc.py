"""OIDC ID-token check (e.g. Microsoft Entra ID). Configured, not hard-coded: see docs/auth.md."""

from functools import lru_cache
from typing import Any

import jwt

from cip_api.settings import Settings


class OidcError(Exception):
    pass


@lru_cache
def _jwks(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True)


def verify_id_token(settings: Settings, id_token: str) -> str:
    """Check signature, issuer, audience and expiry; return the signed-in email (lowercase)."""
    if not (settings.oidc_issuer and settings.oidc_audience and settings.oidc_jwks_url):
        raise OidcError("OIDC is not configured")
    try:
        key = _jwks(settings.oidc_jwks_url).get_signing_key_from_jwt(id_token)
        claims: dict[str, Any] = jwt.decode(
            id_token,
            key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise OidcError(f"ID token rejected: {exc}") from exc
    # Entra ID puts the sign-in name in preferred_username; other providers use email.
    email = claims.get("email") or claims.get("preferred_username")
    if not isinstance(email, str) or "@" not in email:
        raise OidcError("ID token has no email")
    return email.lower()
