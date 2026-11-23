# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
import re

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.errors import InvalidQueryError
from app.schemas.discovery import DiscoverySearchResponse
from app.security.internal_api_key import auth_is_required, require_access_token, token_reference
from app.services.tap_service import TapService
from app.vo.adql import QUERYABLE_COLUMNS
from app.vo.tap_schema import (AVAILABILITY_MEDIA_TYPE, CAPABILITIES_MEDIA_TYPE, TABLESET_MEDIA_TYPE, TAP_MAX_ROWS,
                               availability_xml, obscore_tableset, tap_capabilities_xml)
from app.vo.votable import VOTABLE_MEDIA_TYPE, discovery_results_to_votable, tap_error_votable

router = APIRouter(prefix="/tap", tags=["tap"])


_QVALUE = re.compile(r"^(0(\.[0-9]{0,3})?|1(\.0{0,3})?)$", re.ASCII)
# What the route serves: the JSON summary, or the VOSI document as application/xml.
_JSON, _XML = ("application", "json"), ("application", "xml")


def _split_unquoted(text: str, separator: str) -> list[str]:
    """``text`` split at ``separator`` outside double-quoted strings (a media
    parameter may be a quoted string holding commas or semicolons)."""
    parts, current, quoted, escaped = [], [], False, False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\" and quoted:
            current.append(char)
            escaped = True
        elif char == '"':
            quoted = not quoted
            current.append(char)
        elif char == separator and not quoted:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def _prefers_json(accept: str) -> bool:
    """Whether an Accept header asks for the JSON summary over the XML
    document the route otherwise serves (RFC 9110 12.5.1): each of the two
    takes the quality of the most specific media range that matches it
    (``application/json`` before ``application/*`` before ``*/*``); a range
    whose quality value is malformed is ignored; ties and an empty header
    leave the default, XML."""
    ranges: list[tuple[str, str, float]] = []
    for item in _split_unquoted(accept, ","):
        parts = [p.strip() for p in _split_unquoted(item, ";")]
        media = parts[0].lower()
        if media.count("/") != 1:
            continue
        weight = 1.0
        for param in parts[1:]:
            name, _eq, value = param.partition("=")
            if name.strip().lower() == "q":
                if not _QVALUE.match(value.strip()):
                    weight = None
                    break
                weight = float(value.strip())
        if weight is None:
            continue
        kind, subtype = media.split("/", 1)
        ranges.append((kind, subtype, weight))

    def quality(kind: str, subtype: str) -> float:
        best, best_specificity = 0.0, 0
        for r_kind, r_subtype, weight in ranges:
            if (r_kind, r_subtype) == (kind, subtype):
                specificity = 3
            elif r_kind == kind and r_subtype == "*":
                specificity = 2
            elif (r_kind, r_subtype) == ("*", "*"):
                specificity = 1
            else:
                continue
            if specificity > best_specificity or (specificity == best_specificity and weight > best):
                best, best_specificity = weight, specificity
        return best

    return quality(*_JSON) > quality(*_XML)


@router.get("/capabilities", response_model=None)
def tap_capabilities(request: Request,
                     fmt: str | None = Query(default=None, alias="FORMAT")) -> dict | Response:
    """The VOSI capabilities document (XML), as VO clients read it; the
    service's own JSON summary with ``FORMAT=json`` or an ``Accept`` header
    that prefers ``application/json``."""
    if (fmt or "").lower() != "json" and not _prefers_json(request.headers.get("accept", "")):
        base = settings.public_base_url or str(request.base_url).rstrip("/")
        return Response(content=tap_capabilities_xml(base, auth_required=auth_is_required()),
                        media_type=CAPABILITIES_MEDIA_TYPE)
    return {
        "standard_id": "ivo://ivoa.net/std/TAP",
        "profile": "TAP sync ObsCore compatibility profile",
        "status": "obscore-profile",
        "languages": [{"name": "ADQL", "version": "2.1"}],
        "tables": ["ivoa.ObsCore"],
        "tables_endpoint": "/tap/tables",
        "output_formats": ["application/json", VOTABLE_MEDIA_TYPE],
        "limits": {"MAXREC": TAP_MAX_ROWS},
        "supported_operators": ["=", "!=", "<>", "<", "<=", ">", ">="],
        "supported_geometry": [
            "1 = CONTAINS(POINT('ICRS', s_ra, s_dec), CIRCLE('ICRS', ra, dec, radius))"
        ],
        "queryable_columns": QUERYABLE_COLUMNS,
    }


@router.get("/tables")
def tap_tables() -> Response:
    """VOSI tableset describing ivoa.ObsCore (TAP_SCHEMA equivalent).

    Loaded by VO tools (TOPCAT, pyvo) to discover the queryable columns,
    their datatypes, UCDs and units before building ADQL.
    """
    return Response(content=obscore_tableset(), media_type=TABLESET_MEDIA_TYPE)


_VOTABLE_FORMATS = {"votable", "votable/td", "application/x-votable+xml", "text/xml", "application/xml", "xml"}
_JSON_FORMATS = {"json", "application/json"}
# LANG values a TAP 1.1 client may send for this service's language.
_LANGS = {"ADQL", "ADQL-2.0", "ADQL-2.1"}


def _requested_format(fmt: str | None) -> str:
    # TAP 1.1 RESPONSEFORMAT values as VO clients send them: "votable",
    # "votable/td", or a MIME type with parameters
    # ("application/x-votable+xml;serialization=tabledata"). SKAVA always
    # writes TABLEDATA, so every VOTable variant gets the same document.
    return (fmt or "votable").lower().split(";")[0].strip()


def _maxrec(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        maxrec = int(value)
    except ValueError as exc:
        raise InvalidQueryError("MAXREC must be an integer") from exc
    if not 0 <= maxrec <= TAP_MAX_ROWS:
        raise InvalidQueryError(f"MAXREC must be between 0 and {TAP_MAX_ROWS}")
    return maxrec


def _sync(db: Session, request: str | None, lang: str | None, query: str | None, maxrec: str | None,
          fmt: str | None) -> DiscoverySearchResponse | Response:
    """One sync query. Errors are answered as DALI wants them: a VOTable with
    QUERY_STATUS ERROR (status 400), unless the client asked for JSON, which
    gets SKAVA's JSON error envelope."""
    requested = _requested_format(fmt)
    try:
        if (request or "doQuery").lower() != "doquery":
            raise InvalidQueryError("REQUEST must be doQuery")
        if (lang or "ADQL").upper() not in _LANGS:
            raise InvalidQueryError("LANG must be ADQL")
        if not query or not query.strip():
            raise InvalidQueryError("QUERY is required")
        if requested not in _VOTABLE_FORMATS | _JSON_FORMATS:
            raise InvalidQueryError("Unsupported RESPONSEFORMAT; use votable or application/json")
        limit = _maxrec(maxrec)
        if limit == 0:
            # MAXREC=0: the metadata of the result and no rows (DALI 1.1, 4.4).
            result = TapService(db).run(query=query, maxrec=1)
            result.response.results = []
            result.response.returned = 0
            result.overflow = True
        else:
            result = TapService(db).run(query=query, maxrec=limit)
    except InvalidQueryError as exc:
        if requested in _JSON_FORMATS:
            raise
        return Response(content=tap_error_votable(exc.message), status_code=exc.status_code,
                        media_type=VOTABLE_MEDIA_TYPE)
    if requested in _JSON_FORMATS:
        return result.response
    return Response(content=discovery_results_to_votable(result.response.results, columns=result.columns,
                                                         overflow=result.overflow),
                    media_type=VOTABLE_MEDIA_TYPE)


@router.get("/sync", response_model=None)
def tap_sync_get(
    request: str | None = Query(default=None, alias="REQUEST"),
    lang: str | None = Query(default=None, alias="LANG"),
    query: str | None = Query(default=None, alias="QUERY"),
    maxrec: str | None = Query(default=None, alias="MAXREC"),
    fmt: str | None = Query(default=None, alias="FORMAT"),
    responseformat: str | None = Query(default=None, alias="RESPONSEFORMAT"),
    token: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> DiscoverySearchResponse | Response:
    return _sync(db, request, lang, query, maxrec, responseformat or fmt)


@router.post("/sync", response_model=None)
def tap_sync_post(
    request: str | None = Form(default=None, alias="REQUEST"),
    lang: str | None = Form(default=None, alias="LANG"),
    query: str | None = Form(default=None, alias="QUERY"),
    maxrec: str | None = Form(default=None, alias="MAXREC"),
    fmt: str | None = Form(default=None, alias="FORMAT"),
    responseformat: str | None = Form(default=None, alias="RESPONSEFORMAT"),
    token: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> DiscoverySearchResponse | Response:
    return _sync(db, request, lang, query, maxrec, responseformat or fmt)


@router.get("/availability")
def tap_availability(db: Session = Depends(get_db)) -> Response:
    """VOSI availability: the service is available when its catalogue answers."""
    try:
        db.execute(text("SELECT 1"))
        body = availability_xml(True)
    except SQLAlchemyError:
        body = availability_xml(False, "the catalogue database does not answer")
    return Response(content=body, media_type=AVAILABILITY_MEDIA_TYPE)


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
    job = TapService(db).submit_async_job(query=query, maxrec=maxrec, fmt=fmt,
                                          submitted_by=token_reference(token))
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
