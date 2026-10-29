# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import InvalidQueryError, SKAVAError
from app.ingestion.parsers.csv_parser import parse_csv_bytes
from app.ingestion.parsers.json_parser import parse_json_bytes
from app.schemas.ingestion_job import IngestionJobResponse, IngestionSummaryResponse
from app.security.internal_api_key import require_internal_api_key
from app.services.ingestion_job_service import IngestionJobService, detect_manifest_format

router = APIRouter(prefix="/internal/ingestion", tags=["internal-ingestion"])


def _parse_manifest(payload: bytes, fmt: str) -> list[dict]:
    try:
        if fmt == "csv":
            return parse_csv_bytes(payload)
        if fmt == "json":
            return parse_json_bytes(payload)
    except ValueError as exc:
        raise InvalidQueryError(str(exc)) from exc
    raise InvalidQueryError("Unsupported format. Use csv or json")


@router.post("/dry-run")
async def dry_run_ingestion(
    file: UploadFile = File(...),
    format: str | None = Form(default=None),
    source_ref: str | None = Form(default=None),
    source_type: str | None = Form(default=None),
    _: str = Depends(require_internal_api_key),
    db: Session = Depends(get_db),
) -> dict[str, IngestionJobResponse | IngestionSummaryResponse]:
    payload = await file.read()
    if not payload:
        raise InvalidQueryError("Uploaded file is empty")

    fmt = detect_manifest_format(file.filename, format)
    records = _parse_manifest(payload, fmt)

    svc = IngestionJobService(db)
    job, summary = svc.run_job(
        records,
        dry_run=True,
        source_type=source_type or fmt,
        source_ref=source_ref,
        filename=file.filename,
        triggered_by="internal-api",
    )
    return {"job": job, "summary": summary}


@router.post("/run")
async def run_ingestion(
    file: UploadFile = File(...),
    format: str | None = Form(default=None),
    source_ref: str | None = Form(default=None),
    source_type: str | None = Form(default=None),
    _: str = Depends(require_internal_api_key),
    db: Session = Depends(get_db),
) -> dict[str, IngestionJobResponse | IngestionSummaryResponse]:
    payload = await file.read()
    if not payload:
        raise InvalidQueryError("Uploaded file is empty")

    fmt = detect_manifest_format(file.filename, format)
    records = _parse_manifest(payload, fmt)

    svc = IngestionJobService(db)
    job, summary = svc.run_job(
        records,
        dry_run=False,
        source_type=source_type or fmt,
        source_ref=source_ref,
        filename=file.filename,
        triggered_by="internal-api",
    )
    return {"job": job, "summary": summary}


@router.get("/history", response_model=list[IngestionJobResponse])
def ingestion_history(
    limit: int = 50,
    _: str = Depends(require_internal_api_key),
    db: Session = Depends(get_db),
) -> list[IngestionJobResponse]:
    if limit < 1 or limit > 500:
        raise InvalidQueryError("limit must be between 1 and 500")

    svc = IngestionJobService(db)
    return svc.list_history(limit=limit)


@router.get("/history/{job_id}", response_model=IngestionJobResponse)
def ingestion_history_detail(
    job_id: int,
    _: str = Depends(require_internal_api_key),
    db: Session = Depends(get_db),
) -> IngestionJobResponse:
    svc = IngestionJobService(db)
    result = svc.get_history(job_id)
    if not result:
        class IngestionJobNotFound(SKAVAError):
            status_code = 404
            code = "ingestion_job_not_found"

        raise IngestionJobNotFound(f"Ingestion job '{job_id}' not found")
    return result
