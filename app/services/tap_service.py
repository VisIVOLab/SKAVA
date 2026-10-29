# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import InvalidQueryError
from app.models.tap_job import TapJob
from app.schemas.discovery import DiscoverySearchResponse
from app.services.discovery_service import DiscoveryService
from app.vo.adql import parse_where
from app.vo.query_params import CirclePos

_TOP_RE = re.compile(r"\bTOP\s+(\d+)\b", re.IGNORECASE)
_FROM_OBSCORE_RE = re.compile(r"\bFROM\s+(?:ivoa\.)?ObsCore\b", re.IGNORECASE)
_WHERE_RE = re.compile(r"\bWHERE\b(.+)$", re.IGNORECASE | re.DOTALL)


class TapService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _parse_limit(query: str, maxrec: int | None) -> int:
        top_match = _TOP_RE.search(query)
        top = int(top_match.group(1)) if top_match else None
        requested = top if top is not None else maxrec if maxrec is not None else 100
        return max(1, min(requested, 1000))

    @staticmethod
    def _parse_query(query: str) -> tuple[CirclePos | None, list]:
        """Validate the SELECT/FROM and parse the WHERE clause into a cone
        position and a list of SQLAlchemy column conditions."""
        if not _FROM_OBSCORE_RE.search(query):
            raise InvalidQueryError(
                "Only SELECT queries from ivoa.ObsCore are supported by this TAP profile")

        where_match = _WHERE_RE.search(query)
        if not where_match:
            return None, []
        return parse_where(where_match.group(1))

    def sync_query(self, query: str, maxrec: int | None = None) -> DiscoverySearchResponse:
        query = query.strip().rstrip(";")
        if not query.strip().lower().startswith("select"):
            raise InvalidQueryError("Only SELECT queries are supported")

        pos, conditions = self._parse_query(query)
        limit = self._parse_limit(query, maxrec)
        # ADQL CONTAINS(POINT(s_ra, s_dec), CIRCLE(...)) is centre containment,
        # not the footprint overlap of the discovery API's POS.
        return DiscoveryService(self.db).search(
            pos=pos,
            pos_footprint=False,
            extra_conditions=conditions,
            limit=limit,
            offset=0,
        )

    def submit_async_job(
        self,
        *,
        query: str,
        maxrec: int | None,
        fmt: str,
        submitted_by: str | None = None,
    ) -> TapJob:
        job = TapJob(
            created_at=_utcnow(),
            completed_at=None,
            status="queued",
            query=query,
            maxrec=maxrec,
            format=fmt,
            result_json=None,
            error_message=None,
            submitted_by=submitted_by,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return self._execute_job(job)

    def _execute_job(self, job: TapJob) -> TapJob:
        job.status = "running"
        self.db.add(job)
        self.db.commit()
        try:
            result = self.sync_query(job.query, job.maxrec)
            job.result_json = result.model_dump(mode="json")
            job.status = "completed"
            job.completed_at = _utcnow()
            job.error_message = None
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)
            return job
        except Exception as exc:
            self.db.rollback()
            job.status = "failed"
            job.completed_at = _utcnow()
            job.error_message = str(exc)
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)
            return job

    def get_job(self, job_id: int) -> TapJob | None:
        return self.db.scalar(select(TapJob).where(TapJob.id == job_id))

    @staticmethod
    def job_to_dict(job: TapJob) -> dict[str, Any]:
        return {
            "job_id": job.id,
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "status": job.status,
            "query": job.query,
            "maxrec": job.maxrec,
            "format": job.format,
            "result": job.result_json,
            "error_message": job.error_message,
            "submitted_by": job.submitted_by,
        }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
