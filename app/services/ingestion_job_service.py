# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import InvalidQueryError, SKAVAError
from app.ingestion.services.ingest_service import IngestService
from app.models.ingestion_job import IngestionJob
from app.schemas.ingestion_job import IngestionJobResponse, IngestionSummaryResponse


class ConflictError(SKAVAError):
    status_code = 409
    code = "ingestion_running"


class IngestionExecutionError(SKAVAError):
    status_code = 500
    code = "ingestion_failed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class IngestionJobService:
    def __init__(self, db: Session):
        self.db = db

    def run_job(
        self,
        records: list[dict[str, Any]],
        *,
        dry_run: bool,
        source_type: str | None,
        source_ref: str | None,
        filename: str | None,
        triggered_by: str = "internal-api",
    ) -> tuple[IngestionJobResponse, IngestionSummaryResponse]:
        if self._has_running_job():
            raise ConflictError("An ingestion job is already running")

        job = IngestionJob(
            started_at=_utcnow(),
            completed_at=None,
            status="running",
            source_type=source_type,
            source_ref=source_ref,
            filename=filename,
            dry_run=dry_run,
            record_count=len(records),
            summary_json=None,
            error_message=None,
            triggered_by=triggered_by,
        )

        self.db.add(job)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("An ingestion job is already running") from exc

        self.db.refresh(job)

        try:
            service = IngestService(
                self.db,
                dry_run=dry_run,
                source_type=source_type,
                source_ref=source_ref,
            )
            summary = service.ingest_records(records)
            summary_dict = summary.as_dict()

            job.completed_at = _utcnow()
            job.status = "dry_run" if dry_run else "succeeded"
            job.summary_json = summary_dict
            job.error_message = None
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)

            return self._to_job_response(job), self._to_summary_response(summary_dict)
        except Exception as exc:
            self.db.rollback()
            job.completed_at = _utcnow()
            job.status = "failed"
            job.error_message = str(exc)
            self.db.add(job)
            self.db.commit()
            raise IngestionExecutionError(f"Ingestion job failed: {exc}") from exc

    def list_history(self, limit: int = 50) -> list[IngestionJobResponse]:
        stmt = select(IngestionJob).order_by(IngestionJob.started_at.desc()).limit(limit)
        jobs = self.db.scalars(stmt).all()
        return [self._to_job_response(job) for job in jobs]

    def get_history(self, job_id: int) -> IngestionJobResponse | None:
        job = self.db.scalar(select(IngestionJob).where(IngestionJob.id == job_id))
        if not job:
            return None
        return self._to_job_response(job)

    def _has_running_job(self) -> bool:
        running = self.db.scalar(select(IngestionJob.id).where(IngestionJob.status == "running").limit(1))
        return running is not None

    @staticmethod
    def _to_job_response(job: IngestionJob) -> IngestionJobResponse:
        return IngestionJobResponse(
            job_id=job.id,
            started_at=job.started_at,
            completed_at=job.completed_at,
            status=job.status,
            source_type=job.source_type,
            source_ref=job.source_ref,
            filename=job.filename,
            dry_run=job.dry_run,
            record_count=job.record_count,
            summary=job.summary_json,
            error_message=job.error_message,
            triggered_by=job.triggered_by,
        )

    @staticmethod
    def _to_summary_response(summary: dict[str, Any]) -> IngestionSummaryResponse:
        errors = summary.get("validation_errors", [])
        return IngestionSummaryResponse(
            processed=summary.get("total_records", 0),
            inserted_datasets=summary.get("inserted_datasets", 0),
            updated_datasets=summary.get("updated_datasets", 0),
            inserted_replicas=summary.get("inserted_replicas", 0),
            updated_replicas=summary.get("updated_replicas", 0),
            skipped=summary.get("skipped_records", 0),
            validation_errors=errors,
        )


def detect_manifest_format(filename: str | None, format_hint: str | None) -> str:
    if format_hint:
        lowered = format_hint.lower()
        if lowered in {"csv", "json"}:
            return lowered
        raise InvalidQueryError("Unsupported format. Use csv or json")

    if filename:
        lowered = filename.lower()
        if lowered.endswith(".csv"):
            return "csv"
        if lowered.endswith(".json"):
            return "json"

    raise InvalidQueryError("Cannot detect file format. Provide format=csv|json or file extension")
