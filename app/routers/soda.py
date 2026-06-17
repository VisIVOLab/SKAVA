from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import DatasetNotFoundError, InvalidQueryError
from app.schemas.soda import SodaSyncResponse
from app.security.internal_api_key import require_access_token
from app.services.datalink_service import DataLinkService
from app.services.soda_execution_service import SodaExecutionService
from app.services.soda_service import SodaService
from app.services.staging_service import StagingService
from app.vo.parsers import parse_band, parse_pos, parse_time
from app.vo.soda import normalize_interval, normalize_pos, validate_responseformat

router = APIRouter(prefix="/soda", tags=["soda"])


@router.get("/sync", response_model=SodaSyncResponse)
def soda_sync(
    dataset_id: str | None = Query(default=None, alias="ID"),
    pos: str | None = Query(default=None, alias="POS"),
    band: str | None = Query(default=None, alias="BAND"),
    time_value: str | None = Query(default=None, alias="TIME"),
    responseformat: str | None = Query(default=None, alias="RESPONSEFORMAT"),
    _: str | None = Depends(require_access_token),
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


@router.post("/execute")
def soda_execute(
    dataset_id: str | None = Query(default=None, alias="ID"),
    pos: str | None = Query(default=None, alias="POS"),
    band: str | None = Query(default=None, alias="BAND"),
    time_value: str | None = Query(default=None, alias="TIME"),
    responseformat: str | None = Query(default=None, alias="RESPONSEFORMAT"),
    token: str | None = Depends(require_access_token),
    db: Session = Depends(get_db),
):
    """Execute a SODA subset.

    Two outcomes:
    1. **Real cutout** — when the dataset's best node runs a co-located
       VisIVO backend and serves a ``file://`` replica, the byte-level
       FITS cutout is computed *on the node* and streamed back as
       ``application/fits`` (compute-next-to-data).
    2. **Staging handoff** — otherwise, fall back to the metadata-cache
       control-plane job (unchanged legacy behaviour), so catalogue
       entries without a co-located backend still get a routed access URL.
    """
    if not dataset_id:
        raise InvalidQueryError("ID is required")

    parsed_pos = parse_pos(pos)
    parsed_band = parse_band(band)
    parsed_time = parse_time(time_value)
    validated_format = validate_responseformat(responseformat)

    # Attempt real, compute-next-to-data execution first.
    cutout = SodaExecutionService(db).execute(
        dataset_id=dataset_id,
        pos=parsed_pos,
        band=parsed_band,
        time_value=parsed_time,
        responseformat=validated_format,
    )
    if cutout is not None:
        return StreamingResponse(
            iter([cutout.content]),
            media_type=cutout.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{cutout.filename}"',
                "X-Soda-Applied": cutout.applied,
                "X-Soda-Executed-On": cutout.node_code,
            },
        )

    # Fallback: metadata-cache staging handoff.
    request = {
        "ID": dataset_id,
        "POS": normalize_pos(parsed_pos),
        "BAND": normalize_interval(parsed_band),
        "TIME": normalize_interval(parsed_time),
        "RESPONSEFORMAT": validated_format,
        "mode": "soda-subset-handoff",
    }
    job = StagingService(db).submit_metadata_stage(obs_id=dataset_id, request=request, requested_by=token)
    if not job:
        raise DatasetNotFoundError(f"Dataset '{dataset_id}' not found")
    payload = StagingService.to_dict(job)
    payload["operation"] = {
        "type": "subset",
        "execution_profile": "metadata-cache-handoff",
        "message": "Subset request validated and routed. Byte-level FITS cutout execution requires a node with a co-located VisIVO backend serving a file:// replica.",
    }
    return payload
