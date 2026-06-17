from sqlalchemy import Boolean, Float, String
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

    replicas = relationship("DatasetReplica", back_populates="node", cascade="all, delete-orphan")
