"""Pydantic schemas for the indicators resource."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IndicatorBase(BaseModel):
    indicator_type: str
    indicator_unit: str
    indicator_threshold: float | None = None


class IndicatorCreate(IndicatorBase):
    indicator_id: str


class IndicatorRead(IndicatorCreate):
    model_config = ConfigDict(from_attributes=True)
