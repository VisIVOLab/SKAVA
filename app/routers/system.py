from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ServiceUnavailableError
from app.metrics import metrics_payload
from app.schemas.system import AvailabilityResponse, CapabilitiesResponse, DatabaseHealthResponse
from app.services.capabilities_service import get_capabilities
from app.services.health_service import HealthService

router = APIRouter(tags=["system"])


@router.get("/availability", response_model=AvailabilityResponse)
def availability(
    include_nodes: bool = Query(default=False, description="Include node availability summary"),
    db: Session = Depends(get_db),
) -> AvailabilityResponse:
    svc = HealthService(db)
    result = svc.availability(include_nodes=include_nodes)
    if result.database.status != "ok":
        raise ServiceUnavailableError("Database unreachable")
    return result


@router.get("/health/db", response_model=DatabaseHealthResponse)
def db_health(db: Session = Depends(get_db)) -> DatabaseHealthResponse:
    svc = HealthService(db)
    result = svc.db_health()
    if result.status != "ok":
        raise ServiceUnavailableError("Database unreachable")
    return result


@router.get("/metrics")
def metrics() -> Response:
    payload, content_type = metrics_payload()
    return Response(content=payload, media_type=content_type)


@router.get("/capabilities", response_model=CapabilitiesResponse)
def capabilities() -> CapabilitiesResponse:
    return get_capabilities()
