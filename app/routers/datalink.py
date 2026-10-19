from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import DatasetNotFoundError
from app.schemas.datalink import DataLinkResponse
from app.security.internal_api_key import auth_is_required, require_access_token
from app.services.datalink_service import DataLinkService
from app.vo.votable import VOTABLE_MEDIA_TYPE, datalink_to_votable

router = APIRouter(prefix="/datalink", tags=["datalink"])


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
