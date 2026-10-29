"""OIDC bearer-token validation against an SRCNet-style IAM.

SRCNet services authenticate users with OIDC access tokens issued by a
central IAM (INDIGO IAM, or Keycloak in development) and published through
the issuer's discovery document (``IAM_WELLKNOWN_ENDPOINT``). SKAVA accepts
such a token when its signature verifies against the issuer's key set, it has
not expired, it was issued by that issuer (or by ``SKAVA_OIDC_ISSUER`` when
the service reaches the IAM on a name other than the public one the tokens
carry) and, when ``SKAVA_OIDC_AUDIENCE`` is set, it was issued (or exchanged)
for SKAVA.

The discovery document and the key set are fetched lazily and cached; a key
rotation is picked up because PyJWT's client refetches the set on an unknown
key id.
"""
from __future__ import annotations

import logging
import threading

import httpx
import jwt
from jwt import PyJWKClient

from app.config import settings

logger = logging.getLogger("skava.oidc")

# Asymmetric algorithms only: an IAM never signs access tokens with a shared
# secret, and accepting HS* would let anyone holding the public key forge one.
_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "PS256"]


class OIDCValidationError(Exception):
    pass


def oidc_configured() -> bool:
    return bool(settings.oidc_wellknown or settings.oidc_jwks_uri)


class OIDCValidator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._issuer: str | None = None
        self._jwks: PyJWKClient | None = None

    def _discover(self) -> tuple[str | None, PyJWKClient]:
        with self._lock:
            if self._jwks is not None:
                return self._issuer, self._jwks
            issuer, jwks_uri = None, settings.oidc_jwks_uri
            if settings.oidc_wellknown:
                try:
                    doc = httpx.get(settings.oidc_wellknown, timeout=5.0).json()
                except Exception as exc:          # noqa: BLE001 — reported as an auth failure
                    raise OIDCValidationError(f"IAM discovery failed: {exc}") from exc
                issuer = doc.get("issuer")
                jwks_uri = jwks_uri or doc.get("jwks_uri")
            if settings.oidc_issuer:
                issuer = settings.oidc_issuer
            if not jwks_uri:
                raise OIDCValidationError("IAM discovery document has no jwks_uri")
            self._issuer = issuer
            self._jwks = PyJWKClient(jwks_uri, cache_keys=True, lifespan=300)
            return self._issuer, self._jwks

    def validate(self, token: str) -> dict:
        """The token's claims, or :class:`OIDCValidationError`."""
        issuer, jwks = self._discover()
        try:
            key = jwks.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                key.key,
                algorithms=_ALGORITHMS,
                audience=settings.oidc_audience or None,
                issuer=issuer,
                options={"verify_aud": bool(settings.oidc_audience),
                         "verify_iss": issuer is not None,
                         "require": ["exp", "iat"]},
                leeway=30,
            )
        except jwt.PyJWTError as exc:
            raise OIDCValidationError(str(exc)) from exc
        except Exception as exc:                   # noqa: BLE001 — JWKS fetch / network
            raise OIDCValidationError(f"cannot verify token: {exc}") from exc

    def reset(self) -> None:
        """Forget the cached discovery (tests, configuration changes)."""
        with self._lock:
            self._issuer, self._jwks = None, None


validator = OIDCValidator()
