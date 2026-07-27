"""Ingredient ORM model."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base


class Ingredient(Base):
    __tablename__ = "ingredients"

    ingredient_id: Mapped[str] = mapped_column(String, primary_key=True)
    ingredient_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    functional_class: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)

    experiments: Mapped[list["ExperimentIngredient"]] = relationship(
        back_populates="ingredient"
    )
