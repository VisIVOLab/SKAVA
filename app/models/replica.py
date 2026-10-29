# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DatasetReplica(Base):
    __tablename__ = "dataset_replicas"
    __table_args__ = (UniqueConstraint("dataset_id", "node_id", name="uq_dataset_node"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    remote_path: Mapped[str] = mapped_column(String(512))
    access_endpoint: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="available", nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    dataset = relationship("Dataset", back_populates="replicas")
    node = relationship("Node", back_populates="replicas")
