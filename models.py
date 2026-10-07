import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class FileStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GeoFile(Base):
    __tablename__ = "geo_files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(16))          # "kml" | "shapefile"
    status: Mapped[str] = mapped_column(String(16), default=FileStatus.PROCESSING.value)
    crs: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feature_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    features: Mapped[list["Feature"]] = relationship(
        back_populates="file", cascade="all, delete-orphan", order_by="Feature.index"
    )


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("geo_files.id", ondelete="CASCADE"), index=True)
    index: Mapped[int] = mapped_column(Integer)
    layer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    geometry_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # GeoJSON, original CRS
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    crs: Mapped[str | None] = mapped_column(String(64), nullable=True)
    measurement_status: Mapped[str] = mapped_column(String(16), default="UNSUPPORTED")
    measurement_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    area_sq_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    projected_crs: Mapped[str | None] = mapped_column(String(32), nullable=True)

    file: Mapped[GeoFile] = relationship(back_populates="features")
