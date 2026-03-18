import json
from pathlib import Path
from typing import Any


def parse_json_file(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict) and isinstance(payload.get("records"), list):
        records = payload["records"]
    else:
        raise ValueError("JSON ingestion input must be a list or an object with a 'records' list")

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(records):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid JSON record at index {idx}: expected object")
        normalized.append(item)
    return normalized



def parse_json_bytes(payload: bytes) -> list[dict[str, Any]]:
    data = json.loads(payload.decode("utf-8"))
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict) and isinstance(data.get("records"), list):
        records = data["records"]
    else:
        raise ValueError("JSON ingestion input must be a list or an object with a 'records' list")

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(records):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid JSON record at index {idx}: expected object")
        normalized.append(item)
    return normalized
