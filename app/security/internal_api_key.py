from fastapi import Header

from app.config import settings
from app.errors import SKAVAError
from app.security.oidc import OIDCValidationError, oidc_configured
from app.security.oidc import validator as oidc_validator


class UnauthorizedError(SKAVAError):
    status_code = 401
    code = "unauthorized"


async def require_internal_api_key(x_internal_api_key: str | None = Header(default=None)) -> str:
    if not settings.internal_api_key:
        raise UnauthorizedError("Internal API key is not configured")
    if not x_internal_api_key or x_internal_api_key != settings.internal_api_key:
        raise UnauthorizedError("Invalid or missing internal API key")
    return x_internal_api_key


def auth_is_required() -> bool:
    """Whether discovery/access endpoints need a token at all."""
    return bool(settings.access_token_set) or oidc_configured()


def _challenge() -> dict[str, str]:
    # RFC 6750 Bearer, plus the IVOA SSO "ivoa_bearer" challenge SRCNet
    # services return, pointing the client at the IAM to get a token from.
    value = 'Bearer realm="SKAVA"'
    if settings.oidc_wellknown:
        value += (', ivoa_bearer standard_id="ivo://ivoa.net/sso#BearerToken", '
                  f'access_url="{settings.oidc_wellknown}"')
    return {"WWW-Authenticate": value}


async def require_access_token(
    authorization: str | None = Header(default=None),
    x_skava_access_token: str | None = Header(default=None),
) -> str | None:
    """A static access token (SKAVA_ACCESS_TOKENS) or an OIDC access token from
    the configured IAM. Open when neither is configured."""
    configured = settings.access_token_set
    if not configured and not oidc_configured():
        return None

    token = x_skava_access_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    if token and token in configured:
        return token
    if token and oidc_configured() and token.count(".") == 2:
        try:
            oidc_validator.validate(token)
            return token
        except OIDCValidationError as exc:
            raise UnauthorizedError(f"Invalid access token: {exc}", headers=_challenge()) from exc
    raise UnauthorizedError("Invalid or missing access token", headers=_challenge())
