"""Experiment-ingredient junction ORM model."""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base


class ExperimentIngredient(Base):
    __tablename__ = "experiment_ingredients"

    experiment_id: Mapped[str] = mapped_column(
        String, ForeignKey("experiments.experiment_id"), primary_key=True
    )
    ingredient_id: Mapped[str] = mapped_column(
        String, ForeignKey("ingredients.ingredient_id"), primary_key=True
    )
    concentration: Mapped[float] = mapped_column(Float, nullable=False)
    concentration_unit: Mapped[str] = mapped_column(String, nullable=False)

    experiment: Mapped["Experiment"] = relationship(back_populates="ingredients")
    ingredient: Mapped["Ingredient"] = relationship(back_populates="experiments")
