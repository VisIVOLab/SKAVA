from datetime import datetime
from typing import Any

from pydantic import BaseModel


class IngestionSummaryResponse(BaseModel):
    processed: int
    inserted_datasets: int
    updated_datasets: int
    inserted_replicas: int
    updated_replicas: int
    skipped: int
    validation_errors: list[dict[str, Any]]


class IngestionJobResponse(BaseModel):
    job_id: int
    started_at: datetime
    completed_at: datetime | None
    status: str
    source_type: str | None
    source_ref: str | None
    filename: str | None
    dry_run: bool
    record_count: int
    summary: dict[str, Any] | None
    error_message: str | None
    triggered_by: str | None
