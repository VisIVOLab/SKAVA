from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
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

    access_format: Mapped[str | None] = mapped_column(String(128), nullable=True)
    access_estsize: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)

    replicas = relationship("DatasetReplica", back_populates="dataset", cascade="all, delete-orphan")
