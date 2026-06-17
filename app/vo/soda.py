from app.errors import InvalidQueryError
from app.vo.query_params import CirclePos, NumericInterval

_SUPPORTED_RESPONSE_FORMATS = {
    "application/fits",
    "image/fits",
    "application/octet-stream",
    "application/json",
}


def normalize_pos(value: CirclePos | None) -> str | None:
    if not value:
        return None
    return f"CIRCLE {value.ra} {value.dec} {value.radius}"


def normalize_interval(value: NumericInterval | None) -> str | None:
    if not value:
        return None
    return f"{value.min_value} {value.max_value}"


def validate_responseformat(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized not in _SUPPORTED_RESPONSE_FORMATS:
        raise InvalidQueryError(
            "Unsupported RESPONSEFORMAT. Supported values: application/fits, image/fits, application/octet-stream, application/json"
        )
    return normalized

