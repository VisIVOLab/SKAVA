# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
import re
from dataclasses import dataclass
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
from app.vo.tap_schema import OBSCORE_COLUMN_NAMES

_TOP_RE = re.compile(r"\bTOP\s+(\d+)\b", re.IGNORECASE)
_FROM_OBSCORE_RE = re.compile(r"\bFROM\s+(?:ivoa\.)?ObsCore\b", re.IGNORECASE)
_WHERE_RE = re.compile(r"\bWHERE\b(.+)$", re.IGNORECASE | re.DOTALL)
# The select list: what lies between SELECT [TOP n] and FROM.
_SELECT_LIST_RE = re.compile(r"^\s*SELECT\s+(?:TOP\s+\d+\s+)?(.*?)\s+FROM\b", re.IGNORECASE | re.DOTALL)
# A table name or alias in front of a select-list item (``obscore.s_ra``,
# ``ivoa.ObsCore.*``, ``o.obs_id`` with ``FROM ivoa.ObsCore AS o``).
_QUALIFIER_RE = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*\.)+")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class TapResult:
    """A sync query's answer: the rows, the columns it selected (in order) and
    whether MAXREC cut it (DALI OVERFLOW; a TOP the query asked for is not)."""
    response: DiscoverySearchResponse
    columns: list[tuple[str, str]]   # (ObsCore column, output name)
    overflow: bool


class TapService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _limits(query: str, maxrec: int | None) -> tuple[int, bool]:
        """The number of rows to return, and whether that number is the
        service's cap (MAXREC, or the default and hard limits) rather than the
        query's own TOP: only a cut by the cap is an OVERFLOW (DALI). MAXREC
        caps a TOP too; without MAXREC a TOP is honoured up to the hard limit."""
        top_match = _TOP_RE.search(query)
        top = int(top_match.group(1)) if top_match else None
        cap = min(maxrec, 1000) if maxrec is not None else (1000 if top is not None else 100)
        if top is not None and top <= cap:
            return max(1, top), False
        return max(1, cap), True

    @staticmethod
    def _parse_select_list(query: str) -> list[tuple[str, str]]:
        """The select list as (column, output name) pairs, in order: ``*`` is
        every column of ``ivoa.ObsCore`` under its own name; otherwise column
        names, optionally qualified (``obscore.s_ra``, ``o.s_ra``) and
        optionally renamed (``s_ra AS ra``, ``s_ra ra``). Expressions,
        functions and DISTINCT are outside this profile."""
        match = _SELECT_LIST_RE.match(query)
        if not match:
            raise InvalidQueryError("Expected SELECT [TOP n] <columns> FROM ivoa.ObsCore")
        items = [item.strip() for item in match.group(1).split(",")]
        if len(items) == 1 and _QUALIFIER_RE.sub("", items[0]) == "*":
            return [(name, name) for name in OBSCORE_COLUMN_NAMES]
        columns: list[tuple[str, str]] = []
        for item in items:
            parts = item.split()
            if len(parts) == 3 and parts[1].upper() == "AS":
                parts = [parts[0], parts[2]]
            if len(parts) not in (1, 2) or not all(_IDENTIFIER_RE.match(p) for p in
                                                       [_QUALIFIER_RE.sub("", parts[0])] + parts[1:]):
                raise InvalidQueryError(
                    f"Select list item {item!r} is not supported: list ObsCore columns, or use *")
            name = _QUALIFIER_RE.sub("", parts[0]).lower()
            if name not in OBSCORE_COLUMN_NAMES:
                raise InvalidQueryError(f"Unknown column {parts[0]!r} in ivoa.ObsCore")
            columns.append((name, parts[1] if len(parts) == 2 else name))
        labels = [label.lower() for _, label in columns]
        if len(set(labels)) != len(labels):
            raise InvalidQueryError("Each output column needs its own name")
        return columns

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

    def run(self, query: str, maxrec: int | None = None) -> TapResult:
        query = query.strip().rstrip(";")
        if not query.strip().lower().startswith("select"):
            raise InvalidQueryError("Only SELECT queries are supported")

        pos, conditions = self._parse_query(query)
        columns = self._parse_select_list(query)
        limit, capped = self._limits(query, maxrec)
        # ADQL CONTAINS(POINT(s_ra, s_dec), CIRCLE(...)) is centre containment,
        # not the footprint overlap of the discovery API's POS.
        response = DiscoveryService(self.db).search(
            pos=pos,
            pos_footprint=False,
            extra_conditions=conditions,
            limit=limit,
            offset=0,
        )
        overflow = capped and response.total > limit
        return TapResult(response=response, columns=columns, overflow=overflow)

    def sync_query(self, query: str, maxrec: int | None = None) -> DiscoverySearchResponse:
        return self.run(query, maxrec).response

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
