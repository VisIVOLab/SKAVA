import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import InvalidQueryError
from app.models.tap_job import TapJob
from app.schemas.discovery import DiscoverySearchResponse
from app.services.discovery_service import DiscoveryService

_TOP_RE = re.compile(r"\bTOP\s+(\d+)\b", re.IGNORECASE)
_FROM_OBSCORE_RE = re.compile(r"\bFROM\s+(?:ivoa\.)?ObsCore\b", re.IGNORECASE)
_WHERE_RE = re.compile(r"\bWHERE\b(.+)$", re.IGNORECASE | re.DOTALL)
_EQ_RE = re.compile(r"\b(obs_id|obs_collection|dataproduct_type|spatial_index_cell)\s*=\s*'([^']+)'", re.IGNORECASE)


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
    def _parse_filters(query: str) -> dict[str, str | None]:
        if not _FROM_OBSCORE_RE.search(query):
            raise InvalidQueryError("Only SELECT queries from ivoa.ObsCore are supported by this TAP sync profile")

        filters: dict[str, str | None] = {"obs_id": None, "collection": None, "dptype": None, "spatial_cell": None}
        where_match = _WHERE_RE.search(query)
        if not where_match:
            return filters

        where_clause = where_match.group(1)
        unsupported = re.sub(_EQ_RE, "", where_clause)
        unsupported = re.sub(r"\bAND\b|\s|\(|\)", "", unsupported, flags=re.IGNORECASE)
        if unsupported:
            raise InvalidQueryError("Unsupported ADQL WHERE clause; supported equality predicates: obs_id, obs_collection, dataproduct_type, spatial_index_cell")

        for field, value in _EQ_RE.findall(where_clause):
            normalized = field.lower()
            if normalized == "obs_id":
                filters["obs_id"] = value
            elif normalized == "obs_collection":
                filters["collection"] = value
            elif normalized == "dataproduct_type":
                filters["dptype"] = value
            elif normalized == "spatial_index_cell":
                filters["spatial_cell"] = value
        return filters

    def sync_query(self, query: str, maxrec: int | None = None) -> DiscoverySearchResponse:
        query = query.strip().rstrip(";")
        if not query.strip().lower().startswith("select"):
            raise InvalidQueryError("Only SELECT queries are supported")

        filters = self._parse_filters(query)
        limit = self._parse_limit(query, maxrec)
        return DiscoveryService(self.db).search(
            obs_id=filters["obs_id"],
            collection=filters["collection"],
            dptype=filters["dptype"],
            spatial_cell=filters["spatial_cell"],
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
