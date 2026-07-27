"""Pydantic schemas for the experiment-ingredient junction."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExperimentIngredientBase(BaseModel):
    concentration: float
    concentration_unit: str


class ExperimentIngredientCreate(ExperimentIngredientBase):
    experiment_id: str
    ingredient_id: str


class ExperimentIngredientRead(ExperimentIngredientCreate):
    model_config = ConfigDict(from_attributes=True)
