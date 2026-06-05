from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import DatasetNotFoundError, InvalidQueryError
from app.security.internal_api_key import require_access_token
from app.schemas.discovery import DiscoveryResult, DiscoverySearchResponse
from app.services.discovery_service import DiscoveryService
from app.vo.parsers import parse_band, parse_pos, parse_time

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.get("/search", response_model=DiscoverySearchResponse)
def search(
    obs_id: str | None = Query(default=None),
    pos: str | None = Query(default=None, alias="POS"),
    band: str | None = Query(default=None, alias="BAND"),
    time_value: str | None = Query(default=None, alias="TIME"),
    collection: str | None = Query(default=None, alias="COLLECTION"),
    dptype: str | None = Query(default=None, alias="DPTYPE"),
    spatial_cell: str | None = Query(default=None, alias="SPATIAL_CELL"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> DiscoverySearchResponse:
    if offset > 1_000_000:
        raise InvalidQueryError("offset must be <= 1000000; use narrower scientific filters for deeper scans")

    svc = DiscoveryService(db)
    return svc.search(
        obs_id=obs_id,
        pos=parse_pos(pos),
        band=parse_band(band),
        time_value=parse_time(time_value),
        collection=collection,
        dptype=dptype,
        spatial_cell=spatial_cell,
        limit=limit,
        offset=offset,
    )


@router.get("/dataset/{obs_id}", response_model=DiscoveryResult)
def dataset(
    obs_id: str,
    _: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> DiscoveryResult:
    svc = DiscoveryService(db)
    result = svc.get_dataset(obs_id)
    if not result:
        raise DatasetNotFoundError(f"Dataset '{obs_id}' not found")
    return result
