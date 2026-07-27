"""Drop the legacy flat-extraction table.

`extracted_rows` held free-schema key/value blobs produced by the pre-Docling extractor. It
ran in parallel with the structured `ext_*` tables, and the only bridge from it to the
canonical hierarchy (`canonical_promoter`) now reads `ext_*` directly, so nothing writes or
reads it any more.

Also drops `studies.legacy_row_id`, which existed solely to point back at it and formed a
circular foreign-key pair with `extracted_rows.canonical_study_id`.

Order matters: the FK from studies must go before the table it references, and the
downgrade has to recreate the table before re-adding the constraint.

Revision ID: a1f2c3d4e5b6
Revises: 03bcf150bdbf
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1f2c3d4e5b6"
down_revision: Union[str, None] = "03bcf150bdbf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The named constraint may be absent on databases created by the old create_all path,
    # which produced an auto-named one. Dropping the column removes either.
    with op.batch_alter_table("studies") as batch:
        batch.drop_column("legacy_row_id")

    op.drop_index("ix_extracted_rows_id", table_name="extracted_rows")
    op.drop_table("extracted_rows")


def downgrade() -> None:
    op.create_table(
        "extracted_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=True),
        sa.Column("provenance_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("canonical_study_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["canonical_study_id"], ["studies.id"]),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_extracted_rows_id"), "extracted_rows", ["id"], unique=False
    )

    op.add_column("studies", sa.Column("legacy_row_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_studies_legacy_row_id", "studies", "extracted_rows", ["legacy_row_id"], ["id"]
    )
