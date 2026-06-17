import csv
from pathlib import Path
from typing import Any


def parse_csv_file(path: str | Path) -> list[dict[str, Any]]:
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        records = [dict(row) for row in reader]
    return records



def parse_csv_bytes(payload: bytes) -> list[dict[str, Any]]:
    text = payload.decode("utf-8")
    reader = csv.DictReader(text.splitlines())
    return [dict(row) for row in reader]
