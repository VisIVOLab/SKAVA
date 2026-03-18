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
