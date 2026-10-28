from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    base_url: Mapped[str] = mapped_column(String(512))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    latency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    capability_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Distributed VisIVO backend coordinates ──────────────────────────
    # A node may host a co-located VisIVO backend (FastAPI service that
    # opens dataset files directly from the SRC storage filesystem).
    # When set, the DataLink builder emits a "visivo-backend" entry in
    # the service_descriptors[] array so desktop clients can choose to
    # route compute requests to the SRC instead of downloading the file
    # to the desktop. See docs/distributed-backend-design.md.
    visivo_backend_url: Mapped[str | None] = mapped_column(
            String(256), nullable=True)
    visivo_backend_requires_auth: Mapped[bool] = mapped_column(
            Boolean, server_default="false", nullable=False)

    # ── Measured state of the node's backend (telemetry_service) ─────────
    # Written by SKAVA's prober, read by the resource-aware ranking policy:
    # ``probe_ok`` whether the backend answered the last probe, ``probe_rtt_ms``
    # the median round trip of its /v1/ping, ``telemetry_json`` its
    # /v1/node/status document, ``telemetry_at`` when that was taken (UTC).
    probe_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    probe_rtt_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    probe_error: Mapped[str | None] = mapped_column(String(256), nullable=True)
    telemetry_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    telemetry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    replicas = relationship("DatasetReplica", back_populates="node", cascade="all, delete-orphan")
