# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.staging_job import StagingJob
from app.services.datalink_service import DataLinkService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StagingService:
    def __init__(self, db: Session):
        self.db = db

    def submit_metadata_stage(
        self,
        *,
        obs_id: str,
        request: dict[str, Any],
        requested_by: str | None = None,
    ) -> StagingJob | None:
        datalink = DataLinkService(self.db).resolve(obs_id)
        if not datalink:
            return None

        job = StagingJob(
            created_at=_utcnow(),
            completed_at=_utcnow(),
            status="ready",
            obs_id=obs_id,
            stage_mode="metadata-cache",
            staged_url=datalink.primary_access.access_url,
            request_json=request,
            result_json=datalink.model_dump(mode="json"),
            error_message=None,
            requested_by=requested_by,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job(self, job_id: int) -> StagingJob | None:
        return self.db.scalar(select(StagingJob).where(StagingJob.id == job_id))

    @staticmethod
    def to_dict(job: StagingJob) -> dict[str, Any]:
        return {
            "job_id": job.id,
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "status": job.status,
            "obs_id": job.obs_id,
            "stage_mode": job.stage_mode,
            "staged_url": job.staged_url,
            "request": job.request_json,
            "result": job.result_json,
            "error_message": job.error_message,
            "requested_by": job.requested_by,
        }
