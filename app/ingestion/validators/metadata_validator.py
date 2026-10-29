import re

from sqlalchemy import String

from app.ingestion.base import IngestionRecord
from app.models.dataset import Dataset
from app.models.replica import DatasetReplica


REQUIRED_FIELDS = ("obs_id", "dataproduct_type", "node_id", "access_url")

# SKAVA is a discovery catalogue, not a downloader — it stores access URLs
# but never fetches data from them. So the validator only requires that
# the URL declares some scheme (so the consumer can dispatch), without
# pinning it to HTTP. Consumers (VisIVO backend, etc.) decide which
# schemes they actually honour.
_SCHEME_RX = re.compile(r"^[a-z][a-z0-9+\-.]*://", re.IGNORECASE)

# The width of each text column of the dataset table, read from the model:
# a value longer than its column would fail the whole batch on PostgreSQL
# (SQLite does not enforce widths), so the record is refused here instead.
_TEXT_WIDTHS = {
    column.name: column.type.length
    for column in Dataset.__table__.columns
    if isinstance(column.type, String) and column.type.length
}


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

    for name, width in _TEXT_WIDTHS.items():
        value = getattr(record, name, None)
        if isinstance(value, str) and len(value) > width:
            errors.append(f"{name} is longer than {width} characters")

    url_width = DatasetReplica.__table__.columns["access_endpoint"].type.length
    if record.access_url and len(record.access_url) > url_width:
        errors.append(f"access_url is longer than {url_width} characters")

    if record.access_url and not _SCHEME_RX.match(record.access_url):
        errors.append(
            "access_url must include a scheme (e.g. http://, https://, "
            "file://, ftp://, sftp://)."
        )

    return errors
