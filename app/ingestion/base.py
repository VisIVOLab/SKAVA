from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class IngestionRecord:
    obs_id: str
    dataproduct_type: str
    node_id: str
    access_url: str

    obs_collection: str | None = None
    calib_level: int | None = None
    target_name: str | None = None
    obs_title: str | None = None
    facility_name: str | None = None
    instrument_name: str | None = None
    s_ra: float | None = None
    s_dec: float | None = None
    s_fov: float | None = None
    t_min: float | None = None
    t_max: float | None = None
    em_min: float | None = None
    em_max: float | None = None
    access_format: str | None = None
    access_estsize: int | None = None
    is_public: bool | None = None
    checksum: str | None = None
    source_type: str | None = None
    source_ref: str | None = None
    provenance: dict[str, Any] | None = None
    doi: str | None = None
    pid: str | None = None
    citation: str | None = None
    license: str | None = None


@dataclass
class IngestError:
    index: int
    code: str
    message: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestSummary:
    total_records: int = 0
    inserted_datasets: int = 0
    updated_datasets: int = 0
    inserted_replicas: int = 0
    updated_replicas: int = 0
    skipped_records: int = 0
    validation_errors: list[IngestError] = field(default_factory=list)
    started_at: datetime = field(default_factory=_utcnow)
    finished_at: datetime | None = None

    def finalize(self) -> None:
        self.finished_at = _utcnow()

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "inserted_datasets": self.inserted_datasets,
            "updated_datasets": self.updated_datasets,
            "inserted_replicas": self.inserted_replicas,
            "updated_replicas": self.updated_replicas,
            "skipped_records": self.skipped_records,
            "validation_errors": [
                {"index": e.index, "code": e.code, "message": e.message} for e in self.validation_errors
            ],
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
