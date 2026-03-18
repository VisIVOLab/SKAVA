from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import DatasetNotFoundError
from app.schemas.access import AccessResponse
from app.services.access_service import AccessService

router = APIRouter(prefix="/access", tags=["access"])


@router.get("/{obs_id}", response_model=AccessResponse)
def access(obs_id: str, db: Session = Depends(get_db)) -> AccessResponse:
    svc = AccessService(db)
    result = svc.resolve(obs_id)
    if not result:
        raise DatasetNotFoundError(f"Dataset '{obs_id}' not found")
    return result
