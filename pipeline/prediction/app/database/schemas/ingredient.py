"""Pydantic schemas for the ingredients resource."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IngredientBase(BaseModel):
    ingredient_name: str
    functional_class: str
    source: str


class IngredientCreate(IngredientBase):
    ingredient_id: str


class IngredientRead(IngredientCreate):
    model_config = ConfigDict(from_attributes=True)
