from fastapi import APIRouter, Depends, Form, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import InvalidQueryError
from app.schemas.discovery import DiscoverySearchResponse
from app.security.internal_api_key import require_access_token
from app.services.tap_service import TapService
from app.vo.votable import VOTABLE_MEDIA_TYPE, discovery_results_to_votable

router = APIRouter(prefix="/tap", tags=["tap"])


@router.get("/capabilities")
def tap_capabilities() -> dict:
    return {
        "standard_id": "ivo://ivoa.net/std/TAP",
        "profile": "TAP sync ObsCore compatibility profile",
        "status": "minimal-production-profile",
        "languages": [{"name": "ADQL", "version": "2.1"}],
        "tables": ["ivoa.ObsCore"],
        "output_formats": ["application/json", VOTABLE_MEDIA_TYPE],
        "limits": {"MAXREC": 1000},
        "supported_where_predicates": ["obs_id", "obs_collection", "dataproduct_type"],
    }


def _render_tap_response(result: DiscoverySearchResponse, fmt: str | None) -> DiscoverySearchResponse | Response:
    requested = (fmt or "votable").lower()
    if requested in {"json", "application/json"}:
        return result
    if requested in {"votable", "application/x-votable+xml", "application/xml", "xml"}:
        return Response(content=discovery_results_to_votable(result.results), media_type=VOTABLE_MEDIA_TYPE)
    raise InvalidQueryError("Unsupported FORMAT; use application/json or application/x-votable+xml")


@router.get("/sync", response_model=None)
def tap_sync_get(
    request: str = Query(default="doQuery", alias="REQUEST"),
    lang: str = Query(default="ADQL", alias="LANG"),
    query: str = Query(alias="QUERY"),
    maxrec: int | None = Query(default=None, ge=1, le=1000, alias="MAXREC"),
    fmt: str | None = Query(default=None, alias="FORMAT"),
    token: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> DiscoverySearchResponse | Response:
    if request.lower() != "doquery":
        raise InvalidQueryError("REQUEST must be doQuery")
    if lang.upper() != "ADQL":
        raise InvalidQueryError("LANG must be ADQL")
    result = TapService(db).sync_query(query=query, maxrec=maxrec)
    return _render_tap_response(result, fmt)


@router.post("/sync", response_model=None)
def tap_sync_post(
    request: str = Form(default="doQuery", alias="REQUEST"),
    lang: str = Form(default="ADQL", alias="LANG"),
    query: str = Form(alias="QUERY"),
    maxrec: int | None = Form(default=None, ge=1, le=1000, alias="MAXREC"),
    fmt: str | None = Form(default=None, alias="FORMAT"),
    token: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> DiscoverySearchResponse | Response:
    if request.lower() != "doquery":
        raise InvalidQueryError("REQUEST must be doQuery")
    if lang.upper() != "ADQL":
        raise InvalidQueryError("LANG must be ADQL")
    result = TapService(db).sync_query(query=query, maxrec=maxrec)
    return _render_tap_response(result, fmt)


@router.post("/async")
def tap_async_submit(
    request: str = Form(default="doQuery", alias="REQUEST"),
    lang: str = Form(default="ADQL", alias="LANG"),
    query: str = Form(alias="QUERY"),
    maxrec: int | None = Form(default=None, ge=1, le=1000, alias="MAXREC"),
    fmt: str = Form(default="votable", alias="FORMAT"),
    token: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> dict:
    if request.lower() != "doquery":
        raise InvalidQueryError("REQUEST must be doQuery")
    if lang.upper() != "ADQL":
        raise InvalidQueryError("LANG must be ADQL")
    job = TapService(db).submit_async_job(query=query, maxrec=maxrec, fmt=fmt, submitted_by=token)
    return TapService.job_to_dict(job)


@router.get("/async/{job_id}")
def tap_async_status(
    job_id: int,
    token: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> dict:
    job = TapService(db).get_job(job_id)
    if not job:
        raise InvalidQueryError(f"TAP async job '{job_id}' not found")
    return TapService.job_to_dict(job)
