# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import DatasetNotFoundError
from app.models.dataset import Dataset
from app.security.internal_api_key import require_access_token

router = APIRouter(prefix="/provenance", tags=["provenance"])


@router.get("/{obs_id}")
def provenance(
    obs_id: str,
    _: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> dict:
    dataset = db.scalar(select(Dataset).where(Dataset.obs_id == obs_id))
    if not dataset:
        raise DatasetNotFoundError(f"Dataset '{obs_id}' not found")
    return {
        "obs_id": dataset.obs_id,
        "source_type": dataset.source_type,
        "source_ref": dataset.source_ref,
        "checksum": dataset.checksum,
        "provenance": dataset.provenance_json,
        "doi": dataset.doi,
        "pid": dataset.pid,
        "citation": dataset.citation,
        "license": dataset.license,
        "ingested_at": dataset.ingested_at.isoformat() if dataset.ingested_at else None,
        "updated_at": dataset.updated_at.isoformat() if dataset.updated_at else None,
    }
