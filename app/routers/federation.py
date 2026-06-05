from fastapi import APIRouter, Depends, Query

from app.security.internal_api_key import require_access_token
from app.services.federation_service import FederationService

router = APIRouter(prefix="/federation", tags=["federation"])


@router.get("/sources")
def federation_sources(_: str | None = Depends(require_access_token)) -> dict:
    return {"sources": FederationService().sources()}


@router.get("/search")
def federation_search(
    obs_id: str | None = Query(default=None),
    pos: str | None = Query(default=None, alias="POS"),
    band: str | None = Query(default=None, alias="BAND"),
    time_value: str | None = Query(default=None, alias="TIME"),
    collection: str | None = Query(default=None, alias="COLLECTION"),
    dptype: str | None = Query(default=None, alias="DPTYPE"),
    limit: int = Query(default=100, ge=1, le=1000),
    _: str | None = Depends(require_access_token),
) -> dict:
    return FederationService().search(
        {
            "obs_id": obs_id,
            "POS": pos,
            "BAND": band,
            "TIME": time_value,
            "COLLECTION": collection,
            "DPTYPE": dptype,
            "limit": limit,
        }
    )
