# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
import re

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.errors import InvalidQueryError
from app.schemas.discovery import DiscoverySearchResponse
from app.security.internal_api_key import require_access_token, token_reference
from app.services.tap_service import TapService
from app.vo.adql import QUERYABLE_COLUMNS
from app.vo.tap_schema import (CAPABILITIES_MEDIA_TYPE, TABLESET_MEDIA_TYPE, TAP_MAX_ROWS, obscore_tableset,
                               tap_capabilities_xml)
from app.vo.votable import VOTABLE_MEDIA_TYPE, discovery_results_to_votable

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
        return Response(content=tap_capabilities_xml(base), media_type=CAPABILITIES_MEDIA_TYPE)
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


def _render_tap_response(result: DiscoverySearchResponse, fmt: str | None) -> DiscoverySearchResponse | Response:
    # TAP 1.1 RESPONSEFORMAT values as VO clients send them: "votable",
    # "votable/td", or a MIME type with parameters
    # ("application/x-votable+xml;serialization=tabledata"). SKAVA always
    # writes TABLEDATA, so every VOTable variant gets the same document.
    requested = (fmt or "votable").lower().split(";")[0].strip()
    if requested in {"json", "application/json"}:
        return result
    if requested in {"votable", "votable/td", "application/x-votable+xml", "text/xml",
                     "application/xml", "xml"}:
        return Response(content=discovery_results_to_votable(result.results), media_type=VOTABLE_MEDIA_TYPE)
    raise InvalidQueryError("Unsupported RESPONSEFORMAT; use votable or application/json")


@router.get("/sync", response_model=None)
def tap_sync_get(
    request: str = Query(default="doQuery", alias="REQUEST"),
    lang: str = Query(default="ADQL", alias="LANG"),
    query: str = Query(alias="QUERY"),
    maxrec: int | None = Query(default=None, ge=1, le=1000, alias="MAXREC"),
    fmt: str | None = Query(default=None, alias="FORMAT"),
    responseformat: str | None = Query(default=None, alias="RESPONSEFORMAT"),
    token: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> DiscoverySearchResponse | Response:
    if request.lower() != "doquery":
        raise InvalidQueryError("REQUEST must be doQuery")
    if lang.upper() != "ADQL":
        raise InvalidQueryError("LANG must be ADQL")
    result = TapService(db).sync_query(query=query, maxrec=maxrec)
    return _render_tap_response(result, responseformat or fmt)


@router.post("/sync", response_model=None)
def tap_sync_post(
    request: str = Form(default="doQuery", alias="REQUEST"),
    lang: str = Form(default="ADQL", alias="LANG"),
    query: str = Form(alias="QUERY"),
    maxrec: int | None = Form(default=None, ge=1, le=1000, alias="MAXREC"),
    fmt: str | None = Form(default=None, alias="FORMAT"),
    responseformat: str | None = Form(default=None, alias="RESPONSEFORMAT"),
    token: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> DiscoverySearchResponse | Response:
    if request.lower() != "doquery":
        raise InvalidQueryError("REQUEST must be doQuery")
    if lang.upper() != "ADQL":
        raise InvalidQueryError("LANG must be ADQL")
    result = TapService(db).sync_query(query=query, maxrec=maxrec)
    return _render_tap_response(result, responseformat or fmt)


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
