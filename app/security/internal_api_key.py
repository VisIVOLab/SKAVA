from fastapi import Header

from app.config import settings
from app.errors import SKAVAError


class UnauthorizedError(SKAVAError):
    status_code = 401
    code = "unauthorized"


async def require_internal_api_key(x_internal_api_key: str | None = Header(default=None)) -> str:
    if not settings.internal_api_key:
        raise UnauthorizedError("Internal API key is not configured")
    if not x_internal_api_key or x_internal_api_key != settings.internal_api_key:
        raise UnauthorizedError("Invalid or missing internal API key")
    return x_internal_api_key


async def require_access_token(
    authorization: str | None = Header(default=None),
    x_skava_access_token: str | None = Header(default=None),
) -> str | None:
    configured = settings.access_token_set
    if not configured:
        return None

    token = x_skava_access_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    if not token or token not in configured:
        raise UnauthorizedError("Invalid or missing access token")
    return token
