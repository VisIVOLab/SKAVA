# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.metrics import record_db_error
from app.models.node import Node
from app.schemas.system import AvailabilityResponse, AvailabilitySummary, DatabaseHealthResponse


class HealthService:
    def __init__(self, db: Session):
        self.db = db

    def db_health(self) -> DatabaseHealthResponse:
        try:
            self.db.execute(text("SELECT 1"))
            return DatabaseHealthResponse(status="ok", database="reachable")
        except Exception as exc:
            record_db_error("health_db")
            return DatabaseHealthResponse(status="error", database=f"unreachable: {exc}")

    def availability(self, include_nodes: bool = False) -> AvailabilityResponse:
        db_state = self.db_health()
        if db_state.status != "ok":
            return AvailabilityResponse(status="error", service="skava-discovery", database=db_state, nodes=None)

        node_summary: AvailabilitySummary | None = None
        if include_nodes:
            total = self.db.scalar(select(func.count(Node.id))) or 0
            enabled = self.db.scalar(select(func.count(Node.id)).where(Node.is_enabled.is_(True))) or 0
            available = (
                self.db.scalar(
                    select(func.count(Node.id)).where(Node.is_enabled.is_(True), Node.is_available.is_(True))
                )
                or 0
            )
            node_summary = AvailabilitySummary(total_nodes=total, enabled_nodes=enabled, available_nodes=available)

        overall = "ok"
        if node_summary and node_summary.available_nodes == 0:
            overall = "degraded"

        return AvailabilityResponse(
            status=overall,
            service="skava-discovery",
            database=db_state,
            nodes=node_summary,
        )
