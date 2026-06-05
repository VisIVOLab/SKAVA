from typing import Any

from app.ingestion.base import IngestionRecord


_TRUE_VALUES = {"true", "1", "yes", "y", "t"}
_FALSE_VALUES = {"false", "0", "no", "n", "f"}


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: Any) -> int | None:
    text = _as_str(value)
    if text is None:
        return None
    return int(float(text))


def _as_float(value: Any) -> float | None:
    text = _as_str(value)
    if text is None:
        return None
    return float(text)


def _as_bool(value: Any) -> bool | None:
    text = _as_str(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise ValueError(f"Invalid boolean value '{value}'")


def _as_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return {"value": value}


def normalize_record(raw: dict[str, Any], source_type: str | None = None, source_ref: str | None = None) -> IngestionRecord:
    node_id = _as_str(raw.get("node_id")) or _as_str(raw.get("node_code"))
    access_url = _as_str(raw.get("access_url")) or _as_str(raw.get("access_endpoint"))

    return IngestionRecord(
        obs_id=_as_str(raw.get("obs_id")) or "",
        dataproduct_type=_as_str(raw.get("dataproduct_type")) or "",
        node_id=node_id or "",
        access_url=access_url or "",
        obs_collection=_as_str(raw.get("obs_collection")),
        calib_level=_as_int(raw.get("calib_level")),
        target_name=_as_str(raw.get("target_name")),
        s_ra=_as_float(raw.get("s_ra")),
        s_dec=_as_float(raw.get("s_dec")),
        s_fov=_as_float(raw.get("s_fov")),
        t_min=_as_float(raw.get("t_min")),
        t_max=_as_float(raw.get("t_max")),
        em_min=_as_float(raw.get("em_min")),
        em_max=_as_float(raw.get("em_max")),
        access_format=_as_str(raw.get("access_format")),
        access_estsize=_as_int(raw.get("access_estsize")),
        is_public=_as_bool(raw.get("is_public")),
        checksum=_as_str(raw.get("checksum")),
        source_type=_as_str(raw.get("source_type")) or source_type,
        source_ref=_as_str(raw.get("source_ref")) or source_ref,
        provenance=_as_dict(raw.get("provenance") or raw.get("provenance_json")),
        doi=_as_str(raw.get("doi")),
        pid=_as_str(raw.get("pid")),
        citation=_as_str(raw.get("citation")),
        license=_as_str(raw.get("license")),
    )
