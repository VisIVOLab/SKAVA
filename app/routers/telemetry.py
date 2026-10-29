# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Node telemetry: refresh it on demand, read what the ranking policy sees."""
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.node import Node
from app.security.internal_api_key import UnauthorizedError, require_internal_api_key
from app.security.node_token import verify_node_token
from app.errors import InvalidQueryError
from app.services.telemetry_service import probe_all, store_report

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


class NodeReport(BaseModel):
    """A node's own report of its state: the document its backend serves at
    ``/v1/node/status``, and optionally the round trip it measured on its
    last exchange with the catalogue."""
    node_code: str = Field(min_length=1, max_length=32)
    status: dict
    rtt_ms: float | None = None


@router.post("/internal/telemetry/report")
def report(
    body: NodeReport,
    x_skava_node_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Telemetry pushed by a node, for sites the catalogue cannot probe (a
    firewall in the way, no public status document). The policy reads it as it
    reads a probe; the prober leaves a reporting node alone while its report
    is within the time-to-live.

    Authenticated with the node's own token (``X-Skava-Node-Token``, see
    ``app.security.node_token``): a node can report for itself only, and does
    not hold the catalogue's internal key."""
    if not verify_node_token(body.node_code, x_skava_node_token):
        raise UnauthorizedError("Invalid or missing node token")
    node = db.scalar(select(Node).where(Node.code == body.node_code))
    if node is None or not node.is_enabled:
        raise InvalidQueryError(f"Node not found or disabled: {body.node_code}")
    claimed = body.status.get("node_code")
    if isinstance(claimed, str) and claimed.strip() and claimed.strip() != node.code:
        raise InvalidQueryError(f"The status describes node {claimed.strip()!r}, not {node.code!r}")
    try:
        accepted = store_report(db, node, body.status, body.rtt_ms)
    except ValueError as exc:
        raise InvalidQueryError(f"Invalid node status: {exc}") from exc
    return {"node": node.code, "accepted": accepted}
