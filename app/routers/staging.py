# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import DatasetNotFoundError, InvalidQueryError
from app.security.internal_api_key import require_access_token, token_reference
from app.services.staging_service import StagingService

router = APIRouter(prefix="/staging", tags=["staging"])


@router.post("/jobs")
def submit_staging_job(
    obs_id: str = Query(alias="ID"),
    mode: str = Query(default="metadata-cache"),
    token: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> dict:
    if mode != "metadata-cache":
        raise InvalidQueryError("Only metadata-cache staging mode is implemented in this profile")
    job = StagingService(db).submit_metadata_stage(
        obs_id=obs_id,
        request={"ID": obs_id, "mode": mode},
        requested_by=token_reference(token),
    )
    if not job:
        raise DatasetNotFoundError(f"Dataset '{obs_id}' not found")
    return StagingService.to_dict(job)


@router.get("/jobs/{job_id}")
def get_staging_job(
    job_id: int,
    _: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> dict:
    job = StagingService(db).get_job(job_id)
    if not job:
        raise InvalidQueryError(f"Staging job '{job_id}' not found")
    return StagingService.to_dict(job)
