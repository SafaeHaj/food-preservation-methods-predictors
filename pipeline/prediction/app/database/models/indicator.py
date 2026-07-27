"""Indicator ORM model."""

from __future__ import annotations

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base


class Indicator(Base):
    __tablename__ = "indicators"

    indicator_id: Mapped[str] = mapped_column(String, primary_key=True)
    indicator_type: Mapped[str] = mapped_column(String, nullable=False)
    indicator_unit: Mapped[str] = mapped_column(String, nullable=False)
    indicator_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)

    measurements: Mapped[list["Measurement"]] = relationship(back_populates="indicator")
