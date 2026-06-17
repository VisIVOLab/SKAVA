def validate_pos(value: str | None) -> str | None:
    from app.vo.parsers import parse_pos

    parsed = parse_pos(value)
    if not parsed:
        return None
    return f"CIRCLE {parsed.ra} {parsed.dec} {parsed.radius}"


def validate_interval(name: str, value: str | None) -> str | None:
    from app.vo.parsers import parse_interval

    parsed = parse_interval(name, value)
    if not parsed:
        return None
    return f"{parsed.min_value} {parsed.max_value}"
