"""Pydantic schemas for the experiments resource."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExperimentBase(BaseModel):
    meat_matrix: str
    treatment: str


class ExperimentCreate(ExperimentBase):
    experiment_id: str


class ExperimentRead(ExperimentCreate):
    model_config = ConfigDict(from_attributes=True)
