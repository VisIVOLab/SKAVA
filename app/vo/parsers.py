import re

from app.errors import InvalidQueryError
from app.vo.query_params import CirclePos, NumericInterval

_POS_RE = re.compile(
    r"^CIRCLE\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)


def parse_pos(value: str | None) -> CirclePos | None:
    if value is None:
        return None

    text = value.strip()
    match = _POS_RE.match(text)
    if not match:
        raise InvalidQueryError("POS must use 'CIRCLE <ra> <dec> <radius>' syntax")

    ra = float(match.group(1))
    dec = float(match.group(2))
    radius = float(match.group(3))

    if not (0.0 <= ra <= 360.0):
        raise InvalidQueryError("POS RA must be in [0, 360]")
    if not (-90.0 <= dec <= 90.0):
        raise InvalidQueryError("POS DEC must be in [-90, 90]")
    if radius <= 0.0:
        raise InvalidQueryError("POS radius must be > 0")

    return CirclePos(ra=ra, dec=dec, radius=radius)


def parse_interval(name: str, value: str | None) -> NumericInterval | None:
    if value is None:
        return None

    text = value.strip().replace("/", " ")
    parts = [p for p in text.split() if p]
    if len(parts) != 2:
        raise InvalidQueryError(f"{name} must contain exactly two numeric values")

    try:
        lo = float(parts[0])
        hi = float(parts[1])
    except ValueError as exc:
        raise InvalidQueryError(f"{name} contains non-numeric values") from exc

    if lo > hi:
        raise InvalidQueryError(f"{name} requires min <= max")

    return NumericInterval(min_value=lo, max_value=hi)


def parse_band(value: str | None) -> NumericInterval | None:
    return parse_interval("BAND", value)


def parse_time(value: str | None) -> NumericInterval | None:
    return parse_interval("TIME", value)

