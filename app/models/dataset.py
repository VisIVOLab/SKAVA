# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime

from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)
    obs_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    obs_collection: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    obs_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    dataproduct_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    calib_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    facility_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    instrument_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    s_ra: Mapped[float | None] = mapped_column(Float, nullable=True)
    s_dec: Mapped[float | None] = mapped_column(Float, nullable=True)
    s_fov: Mapped[float | None] = mapped_column(Float, nullable=True)
    t_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    t_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    em_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    em_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    spatial_index_order: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    spatial_index_cell: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    access_format: Mapped[str | None] = mapped_column(String(128), nullable=True)
    access_estsize: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provenance_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(256), nullable=True)
    pid: Mapped[str | None] = mapped_column(String(256), nullable=True)
    citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    license: Mapped[str | None] = mapped_column(String(128), nullable=True)

    replicas = relationship("DatasetReplica", back_populates="dataset", cascade="all, delete-orphan")
