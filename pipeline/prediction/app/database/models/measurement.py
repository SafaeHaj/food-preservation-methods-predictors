"""Measurement ORM model (longitudinal observations)."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base


class Measurement(Base):
    __tablename__ = "measurements"
    __table_args__ = (
        CheckConstraint("day >= 0", name="ck_measurements_day_non_negative"),
    )

    experiment_id: Mapped[str] = mapped_column(
        String, ForeignKey("experiments.experiment_id"), primary_key=True
    )
    day: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicator_id: Mapped[str] = mapped_column(
        String, ForeignKey("indicators.indicator_id"), primary_key=True
    )
    indicator_value: Mapped[float] = mapped_column(Float, nullable=False)

    experiment: Mapped["Experiment"] = relationship(back_populates="measurements")
    indicator: Mapped["Indicator"] = relationship(back_populates="measurements")
