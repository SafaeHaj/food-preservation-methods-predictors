"""Repository for ingredients."""

from __future__ import annotations

from sqlalchemy import select

from app.database.models.ingredient import Ingredient
from app.database.repositories.base import BaseRepository


class IngredientRepository(BaseRepository[Ingredient]):
    model = Ingredient

    def get_by_name(self, name: str) -> Ingredient | None:
        return self.db.scalar(
            select(Ingredient).where(Ingredient.ingredient_name == name)
        )
