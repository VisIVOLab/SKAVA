from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import DatasetNotFoundError
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
    db: Session = Depends(get_db),
) -> DiscoverySearchResponse:
    svc = DiscoveryService(db)
    return svc.search(
        obs_id=obs_id,
        pos=parse_pos(pos),
        band=parse_band(band),
        time_value=parse_time(time_value),
        collection=collection,
        dptype=dptype,
    )


@router.get("/dataset/{obs_id}", response_model=DiscoveryResult)
def dataset(obs_id: str, db: Session = Depends(get_db)) -> DiscoveryResult:
    svc = DiscoveryService(db)
    result = svc.get_dataset(obs_id)
    if not result:
        raise DatasetNotFoundError(f"Dataset '{obs_id}' not found")
    return result
