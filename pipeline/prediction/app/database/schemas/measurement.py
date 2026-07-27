"""Pydantic schemas for the measurements resource."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MeasurementBase(BaseModel):
    day: int = Field(ge=0)
    indicator_value: float


class MeasurementCreate(MeasurementBase):
    experiment_id: str
    indicator_id: str


class MeasurementRead(MeasurementCreate):
    model_config = ConfigDict(from_attributes=True)
