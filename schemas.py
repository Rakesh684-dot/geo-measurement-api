from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_type: str
    feature_count: int
    crs: str | None
    status: str
    error: str | None = None
    created_at: datetime


class FeatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    layer: str | None
    geometry_type: str | None
    crs: str | None
    geometry: dict[str, Any] | None
    properties: dict[str, Any]


class MeasurementOut(BaseModel):
    index: int
    layer: str | None
    geometry_type: str | None
    crs: str | None
    projected_crs: str | None
    status: str                      # MEASURED | NOT_REQUIRED | UNSUPPORTED
    area_sq_m: float | None
    length_m: float | None
    note: str | None


class MeasurementSummary(BaseModel):
    total_area_sq_m: float
    total_length_m: float
    measured: int
    not_required: int
    unsupported: int


class MeasurementsResponse(BaseModel):
    file_id: str
    total: int
    limit: int
    offset: int
    summary: MeasurementSummary
    measurements: list[MeasurementOut]


class FeaturesResponse(BaseModel):
    file_id: str
    total: int
    limit: int
    offset: int
    features: list[FeatureOut]
