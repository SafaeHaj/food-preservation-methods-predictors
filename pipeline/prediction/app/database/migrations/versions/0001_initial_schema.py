"""initial 5-table schema

Revision ID: 0001
Revises:
Create Date: 2026-07-20
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("experiment_id", sa.String(), primary_key=True),
        sa.Column("meat_matrix", sa.String(), nullable=False),
        sa.Column("treatment", sa.String(), nullable=False),
    )
    op.create_table(
        "ingredients",
        sa.Column("ingredient_id", sa.String(), primary_key=True),
        sa.Column("ingredient_name", sa.String(), nullable=False, unique=True),
        sa.Column("functional_class", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
    )
    op.create_table(
        "indicators",
        sa.Column("indicator_id", sa.String(), primary_key=True),
        sa.Column("indicator_type", sa.String(), nullable=False),
        sa.Column("indicator_unit", sa.String(), nullable=False),
        sa.Column("indicator_threshold", sa.Float(), nullable=True),
    )
    op.create_table(
        "experiment_ingredients",
        sa.Column("experiment_id", sa.String(), nullable=False),
        sa.Column("ingredient_id", sa.String(), nullable=False),
        sa.Column("concentration", sa.Float(), nullable=False),
        sa.Column("concentration_unit", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.experiment_id"]),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.ingredient_id"]),
        sa.PrimaryKeyConstraint("experiment_id", "ingredient_id"),
    )
    op.create_table(
        "measurements",
        sa.Column("experiment_id", sa.String(), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("indicator_id", sa.String(), nullable=False),
        sa.Column("indicator_value", sa.Float(), nullable=False),
        sa.CheckConstraint("day >= 0", name="ck_measurements_day_non_negative"),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.experiment_id"]),
        sa.ForeignKeyConstraint(["indicator_id"], ["indicators.indicator_id"]),
        sa.PrimaryKeyConstraint("experiment_id", "day", "indicator_id"),
    )


def downgrade() -> None:
    op.drop_table("measurements")
    op.drop_table("experiment_ingredients")
    op.drop_table("indicators")
    op.drop_table("ingredients")
    op.drop_table("experiments")
