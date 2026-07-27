"""Give every foreign key an explicit ON DELETE policy.

Deleting a paper was impossible: `jobs.paper_id` referenced `papers.id` with no ondelete
and no ORM relationship, so neither Postgres nor SQLAlchemy cleared it and the delete died
on `jobs_paper_id_fkey`. Deleting a project failed the same way but wider -- `Project` had
ORM cascades for 7 children and nothing at all for `jobs`, `audit_events`, `microorganisms`,
`model_runs`, `lab_training_runs`, `lab_model_results`, `imputation_proposals`,
`trajectory_definitions` and `uploaded_datasets`.

67 of 83 foreign keys had no policy. This revision repoints the 65 that need one (16
already carried CASCADE from the baseline) following the five rules documented at the top
of `shared/db/models.py`:

  1. Tenancy root (anything scoped to projects.id)  → CASCADE
  2. Ownership (child cannot exist without parent)  → CASCADE
  3. Provenance (nullable pointer at the producing work) → SET NULL
  4. Attribution (nullable users.id)                → SET NULL
  5. Cross-reference (nullable optional sibling)    → SET NULL

Left deliberately RESTRICT: `projects.owner_id` and `project_members.user_id`. Both are
NOT NULL and there is no user-delete endpoint; failing loudly beats orphaning a project.

Constraint names are discovered from the database rather than assumed. The baseline created
these unnamed, so Postgres auto-named them `<table>_<column>_fkey`, but a database built by
the older `create_all` path may carry different names.

Revision ID: b7d4e9a2c1f3
Revises: a1f2c3d4e5b6
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d4e9a2c1f3"
down_revision: Union[str, None] = "a1f2c3d4e5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: (table, column, target table, ondelete). Target PK is always `id`.
_POLICY: tuple[tuple[str, str, str, str], ...] = (
    # ── Rule 1: tenancy root — everything scoped to a project dies with it ────────
    ("audit_events",           "project_id",            "projects",               "CASCADE"),
    ("dataset_snapshots",      "project_id",            "projects",               "CASCADE"),
    ("export_runs",            "project_id",            "projects",               "CASCADE"),
    ("imputation_proposals",   "project_id",            "projects",               "CASCADE"),
    ("jobs",                   "project_id",            "projects",               "CASCADE"),
    ("lab_model_results",      "project_id",            "projects",               "CASCADE"),
    ("lab_training_runs",      "project_id",            "projects",               "CASCADE"),
    # Nullable, where NULL means "global taxonomy" — those rows hold NULL and are untouched.
    ("microorganisms",         "project_id",            "projects",               "CASCADE"),
    ("model_runs",             "project_id",            "projects",               "CASCADE"),
    ("normalization_mappings", "project_id",            "projects",               "CASCADE"),
    ("papers",                 "project_id",            "projects",               "CASCADE"),
    ("project_members",        "project_id",            "projects",               "CASCADE"),
    ("studies",                "project_id",            "projects",               "CASCADE"),
    ("threshold_definitions",  "project_id",            "projects",               "CASCADE"),
    ("trajectory_definitions", "project_id",            "projects",               "CASCADE"),
    ("uploaded_datasets",      "project_id",            "projects",               "CASCADE"),

    # ── Rule 2: ownership — structural NOT NULL edges ────────────────────────────
    ("experiment_microorganisms", "experiment_id",      "experiments",            "CASCADE"),
    ("experiment_microorganisms", "microorganism_id",   "microorganisms",         "CASCADE"),
    ("experiments",            "study_id",              "studies",                "CASCADE"),
    ("extraction_runs",        "paper_id",              "papers",                 "CASCADE"),
    ("lab_model_results",      "training_run_id",       "lab_training_runs",      "CASCADE"),
    ("lab_training_runs",      "dataset_id",            "uploaded_datasets",      "CASCADE"),
    ("model_fits",             "run_id",                "model_runs",             "CASCADE"),
    ("model_predictions",      "fit_id",                "model_fits",             "CASCADE"),
    ("model_runs",             "trajectory_id",         "trajectory_definitions", "CASCADE"),
    ("observations",           "treatment_arm_id",      "treatment_arms",         "CASCADE"),
    ("treatment_arms",         "experiment_id",         "experiments",            "CASCADE"),

    # ── Rule 3: provenance — the row outlives the work that produced it ──────────
    # `jobs.paper_id` is the bug this revision exists for: SET NULL, not CASCADE, so a
    # deleted paper does not take its run history with it.
    ("jobs",                   "paper_id",              "papers",                 "SET NULL"),
    ("studies",                "paper_id",              "papers",                 "SET NULL"),
    ("ext_experiments",        "job_id",                "jobs",                   "SET NULL"),
    ("extraction_assets",      "job_id",                "jobs",                   "SET NULL"),
    ("extraction_runs",        "job_id",                "jobs",                   "SET NULL"),
    ("lab_training_runs",      "job_id",                "jobs",                   "SET NULL"),
    ("observations",           "extraction_run_id",     "extraction_runs",        "SET NULL"),

    # ── Rule 4: attribution — nullable users.id ──────────────────────────────────
    ("audit_events",           "actor_id",              "users",                  "SET NULL"),
    ("dataset_snapshots",      "created_by",            "users",                  "SET NULL"),
    ("experiments",            "created_by",            "users",                  "SET NULL"),
    ("experiments",            "updated_by",            "users",                  "SET NULL"),
    ("export_runs",            "created_by",            "users",                  "SET NULL"),
    ("imputation_proposals",   "created_by",            "users",                  "SET NULL"),
    ("imputation_proposals",   "reviewer_id",           "users",                  "SET NULL"),
    ("jobs",                   "created_by",            "users",                  "SET NULL"),
    ("lab_training_runs",      "created_by",            "users",                  "SET NULL"),
    ("model_runs",             "created_by",            "users",                  "SET NULL"),
    ("normalization_mappings", "created_by",            "users",                  "SET NULL"),
    ("observations",           "created_by",            "users",                  "SET NULL"),
    ("observations",           "updated_by",            "users",                  "SET NULL"),
    ("project_members",        "invited_by",            "users",                  "SET NULL"),
    ("studies",                "created_by",            "users",                  "SET NULL"),
    ("studies",                "updated_by",            "users",                  "SET NULL"),
    ("threshold_definitions",  "created_by",            "users",                  "SET NULL"),
    ("trajectory_definitions", "created_by",            "users",                  "SET NULL"),
    ("treatment_arms",         "created_by",            "users",                  "SET NULL"),
    ("uploaded_datasets",      "uploader_id",           "users",                  "SET NULL"),

    # ── Rule 5: optional cross-references ────────────────────────────────────────
    ("export_runs",            "snapshot_id",           "dataset_snapshots",      "SET NULL"),
    ("imputation_proposals",   "fit_id",                "model_fits",             "SET NULL"),
    ("imputation_proposals",   "target_arm_id",         "treatment_arms",         "SET NULL"),
    ("imputation_proposals",   "target_observation_id", "observations",           "SET NULL"),
    ("imputation_proposals",   "trajectory_id",         "trajectory_definitions", "SET NULL"),
    # Half of the model_runs <-> model_fits circular pair (declared use_alter in the model).
    ("model_runs",             "selected_model_id",     "model_fits",             "SET NULL"),
    ("observations",           "microorganism_id",      "microorganisms",         "SET NULL"),
    ("trajectory_definitions", "experiment_id",         "experiments",            "SET NULL"),
    ("trajectory_definitions", "microorganism_id",      "microorganisms",         "SET NULL"),
    ("trajectory_definitions", "treatment_arm_id",      "treatment_arms",         "SET NULL"),
    ("treatment_arms",         "control_arm_id",        "treatment_arms",         "SET NULL"),
)


def _constraint_name(inspector, table: str, column: str) -> str | None:
    """The FK currently constraining `table.column`, whatever it happens to be called."""
    for fk in inspector.get_foreign_keys(table):
        if fk["constrained_columns"] == [column] and fk.get("name"):
            return fk["name"]
    return None


def _repoint(table: str, column: str, target: str, ondelete: str | None) -> None:
    """Replace the FK on `table.column` with one carrying `ondelete`."""
    inspector = sa.inspect(op.get_bind())
    existing = _constraint_name(inspector, table, column)
    if existing:
        op.drop_constraint(existing, table, type_="foreignkey")
    op.create_foreign_key(
        f"fk_{table}_{column}", table, target, [column], ["id"], ondelete=ondelete
    )


def upgrade() -> None:
    for table, column, target, ondelete in _POLICY:
        _repoint(table, column, target, ondelete)


def downgrade() -> None:
    """Restore the unpoliced constraints. Deleting a paper or project breaks again."""
    for table, column, target, _ in _POLICY:
        _repoint(table, column, target, None)
