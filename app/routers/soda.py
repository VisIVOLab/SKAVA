from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import DatasetNotFoundError, InvalidQueryError
from app.schemas.soda import SodaSyncResponse
from app.services.datalink_service import DataLinkService
from app.services.soda_service import SodaService
from app.vo.parsers import parse_band, parse_pos, parse_time
from app.vo.soda import validate_responseformat

router = APIRouter(prefix="/soda", tags=["soda"])


@router.get("/sync", response_model=SodaSyncResponse)
def soda_sync(
    dataset_id: str | None = Query(default=None, alias="ID"),
    pos: str | None = Query(default=None, alias="POS"),
    band: str | None = Query(default=None, alias="BAND"),
    time_value: str | None = Query(default=None, alias="TIME"),
    responseformat: str | None = Query(default=None, alias="RESPONSEFORMAT"),
    db: Session = Depends(get_db),
) -> SodaSyncResponse:
    if not dataset_id:
        raise InvalidQueryError("ID is required")

    svc = SodaService(DataLinkService(db))
    result = svc.resolve_sync_stub(
        dataset_id=dataset_id,
        pos=parse_pos(pos),
        band=parse_band(band),
        time_value=parse_time(time_value),
        responseformat=validate_responseformat(responseformat),
    )
    if not result:
        raise DatasetNotFoundError(f"Dataset '{dataset_id}' not found")
    return result

