from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import DatasetNotFoundError
from app.schemas.datalink import DataLinkResponse
from app.services.datalink_service import DataLinkService

router = APIRouter(prefix="/datalink", tags=["datalink"])


@router.get("/{obs_id}", response_model=DataLinkResponse)
def datalink(obs_id: str, db: Session = Depends(get_db)) -> DataLinkResponse:
    svc = DataLinkService(db)
    result = svc.resolve(obs_id)
    if not result:
        raise DatasetNotFoundError(f"Dataset '{obs_id}' not found")
    return result

