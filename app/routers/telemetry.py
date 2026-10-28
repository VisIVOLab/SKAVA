"""Node telemetry: refresh it on demand, read what the ranking policy sees."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.node import Node
from app.security.internal_api_key import require_internal_api_key
from app.services.telemetry_service import probe_all

router = APIRouter(tags=["telemetry"])


def _node_view(node: Node) -> dict:
    return {
        "code": node.code,
        "probe_ok": node.probe_ok,
        "probe_rtt_ms": node.probe_rtt_ms,
        "probe_error": node.probe_error,
        "telemetry_at": node.telemetry_at.isoformat() + "Z" if node.telemetry_at else None,
        "status": node.telemetry_json,
    }


@router.post("/internal/telemetry/probe")
async def probe_now(
    _: str = Depends(require_internal_api_key),
    db: Session = Depends(get_db),
) -> dict:
    """Probe every node now (operators, experiments) instead of waiting for the next cycle."""
    results = await probe_all(db)
    return {"probed": len(results), "ok": sum(r.ok for r in results)}


@router.get("/internal/telemetry")
def telemetry(
    _: str = Depends(require_internal_api_key),
    db: Session = Depends(get_db),
) -> dict:
    """The stored telemetry of every node, with the policy that reads it."""
    nodes = db.scalars(select(Node).order_by(Node.code)).all()
    return {
        "policy": settings.ranking_policy,
        "ttl_seconds": settings.telemetry_ttl_seconds,
        "interval_seconds": settings.telemetry_interval_seconds,
        "nodes": [_node_view(n) for n in nodes],
    }
