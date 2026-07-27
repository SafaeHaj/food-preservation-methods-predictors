"""Experiment ORM model."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base


class Experiment(Base):
    __tablename__ = "experiments"

    experiment_id: Mapped[str] = mapped_column(String, primary_key=True)
    meat_matrix: Mapped[str] = mapped_column(String, nullable=False)
    treatment: Mapped[str] = mapped_column(String, nullable=False)

    ingredients: Mapped[list["ExperimentIngredient"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )
    measurements: Mapped[list["Measurement"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )
