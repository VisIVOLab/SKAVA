from app.ingestion.base import IngestionRecord


REQUIRED_FIELDS = ("obs_id", "dataproduct_type", "node_id", "access_url")


def validate_record(record: IngestionRecord) -> list[str]:
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        value = getattr(record, field)
        if value is None or str(value).strip() == "":
            errors.append(f"Missing required field: {field}")

    if record.s_ra is not None and not (0.0 <= record.s_ra <= 360.0):
        errors.append("s_ra must be in [0, 360]")

    if record.s_dec is not None and not (-90.0 <= record.s_dec <= 90.0):
        errors.append("s_dec must be in [-90, 90]")

    if record.s_fov is not None and record.s_fov <= 0.0:
        errors.append("s_fov must be > 0")

    if record.t_min is not None and record.t_max is not None and record.t_min > record.t_max:
        errors.append("t_min must be <= t_max")

    if record.em_min is not None and record.em_max is not None and record.em_min > record.em_max:
        errors.append("em_min must be <= em_max")

    if record.access_url and not record.access_url.startswith(("http://", "https://")):
        errors.append("access_url must start with http:// or https://")

    return errors
