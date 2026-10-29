from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.federation import FederatedSearchResponse
from app.security.internal_api_key import presented_token, require_access_token
from app.services.discovery_service import DiscoveryService
from app.services.federation_service import FederationService
from app.vo.parsers import parse_band, parse_pos, parse_time

router = APIRouter(prefix="/federation", tags=["federation"])


@router.get("/sources")
def federation_sources(_: str | None = Depends(require_access_token)) -> dict:
    return {"sources": FederationService().sources()}


@router.get("/search", response_model=FederatedSearchResponse)
def federation_search(
    obs_id: str | None = Query(default=None),
    pos: str | None = Query(default=None, alias="POS"),
    band: str | None = Query(default=None, alias="BAND"),
    time_value: str | None = Query(default=None, alias="TIME"),
    collection: str | None = Query(default=None, alias="COLLECTION"),
    dptype: str | None = Query(default=None, alias="DPTYPE"),
    limit: int = Query(default=100, ge=1, le=1000),
    _: str | None = Depends(require_access_token),
    token: str | None = Depends(presented_token),
    db: Session = Depends(get_db),
) -> FederatedSearchResponse:
    """The local catalogue and every configured sibling, merged on ``obs_id``
    (see app/services/federation_service.py). The caller's token, as
    presented, is what the siblings are asked with (an open instance
    forwards it unverified; the siblings verify it)."""
    params = {"obs_id": obs_id, "POS": pos, "BAND": band, "TIME": time_value,
              "COLLECTION": collection, "DPTYPE": dptype}

    def local():
        return DiscoveryService(db).search(obs_id=obs_id, pos=parse_pos(pos), band=parse_band(band),
                                           time_value=parse_time(time_value), collection=collection,
                                           dptype=dptype, limit=limit)

    return FederationService(token=token).search(params, limit, local)
