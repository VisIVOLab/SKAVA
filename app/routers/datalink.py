# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, Form, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import DatasetNotFoundError, InvalidQueryError, NoAvailableNodesError
from app.schemas.datalink import DataLinkResponse
from app.security.internal_api_key import auth_is_required, require_access_token
from app.services.datalink_service import DataLinkService
from app.vo.votable import VOTABLE_MEDIA_TYPE, datalink_links_votable, datalink_to_votable

router = APIRouter(prefix="/datalink", tags=["datalink"])

# The {links} endpoint answers at most this many IDs per request; beyond it
# the response holds the first ones and says OVERFLOW (DataLink 1.1).
MAX_LINKS_IDS = 100
_VOTABLE_FORMATS = {"votable", "application/x-votable+xml", "text/xml", "application/xml"}


def _links(ids: list[str], responseformat: str | None, db: Session) -> Response:
    fmt = (responseformat or "").split(";")[0].strip().lower()
    if fmt and fmt not in _VOTABLE_FORMATS:
        raise InvalidQueryError(f"RESPONSEFORMAT {responseformat!r} is not supported; the {{links}} "
                                "endpoint answers in VOTable")
    # No ID is a valid request with an empty answer (DataLink 1.1).
    ids = [i for i in ids if i and i.strip()]
    svc = DataLinkService(db)
    entries = []
    for requested in ids[:MAX_LINKS_IDS]:
        # Each ID answers on its own: a dataset no node can serve now is a
        # transient fault of its row, not of the whole response.
        try:
            entries.append((requested, svc.resolve(requested)))
        except NoAvailableNodesError as exc:
            entries.append((requested, f"TransientFault: {exc}"))
    return Response(content=datalink_links_votable(entries, auth_required=auth_is_required(),
                                                   overflow=len(ids) > MAX_LINKS_IDS),
                    media_type=VOTABLE_MEDIA_TYPE)


@router.get("", response_model=None)
def links_get(
    ids: list[str] = Query(default=[], alias="ID"),
    responseformat: str | None = Query(default=None, alias="RESPONSEFORMAT"),
    _: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> Response:
    """The DataLink 1.1 {links} endpoint: one or more ``ID``, a VOTable by
    default. ``/datalink/{obs_id}`` is SKAVA's resource for one dataset, JSON
    by default."""
    return _links(ids, responseformat, db)


@router.post("", response_model=None)
def links_post(
    ids: list[str] = Form(default=[], alias="ID"),
    responseformat: str | None = Form(default=None, alias="RESPONSEFORMAT"),
    _: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> Response:
    return _links(ids, responseformat, db)


@router.get("/{obs_id}", response_model=None)
def datalink(
    obs_id: str,
    responseformat: str | None = Query(default=None, alias="RESPONSEFORMAT"),
    format_value: str | None = Query(default=None, alias="FORMAT"),
    _: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> DataLinkResponse | Response:
    svc = DataLinkService(db)
    result = svc.resolve(obs_id)
    if not result:
        raise DatasetNotFoundError(f"Dataset '{obs_id}' not found")
    requested_format = (responseformat or format_value or "json").lower()
    if requested_format in {"votable", "application/x-votable+xml", "application/xml", "xml"}:
        return Response(content=datalink_to_votable(result, auth_required=auth_is_required()),
                        media_type=VOTABLE_MEDIA_TYPE)
    return result
