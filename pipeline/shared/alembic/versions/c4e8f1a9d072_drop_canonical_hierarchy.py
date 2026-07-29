"""Drop the parallel canonical hierarchy and un-prefix the scientific schema.

Two schemas modelled the same science side by side. The `ext_*` tables are what the
Docling/LLM pipeline actually writes; the Study -> Experiment -> TreatmentArm -> Observation
hierarchy beside them was populated by nothing but a promoter that transcribed those very
rows into it, and the modelling stack built on top (trajectories, model fits, imputations,
threshold definitions, snapshots, exports, the model lab) had no other data source.

This revision deletes that second hierarchy and promotes the survivor to the unprefixed
names it was always shadowing. Both halves must happen in one revision and in this order:
`ext_experiments` cannot become `experiments` until the legacy `experiments` table is gone.

Dropped (19 tables)::

    studies, experiments, experiment_microorganisms, treatment_arms, observations,
    microorganisms, normalization_mappings, trajectory_definitions,
    trajectory_observations, model_runs, model_fits, model_predictions,
    imputation_proposals, threshold_definitions, dataset_snapshots, export_runs,
    uploaded_datasets, lab_training_runs, lab_model_results

`model_runs` and `model_fits` reference each other, so the deferred half of that pair
(`fk_model_runs_selected_model_id`, declared `use_alter` in the model) has to be dropped as
a constraint before either table can go. It is resolved by reflection rather than by name:
a database created by the old `create_all` path carries an auto-generated name instead.

Renamed (6 tables, with their indexes and unique constraints)::

    ext_ingredients            -> ingredients
    ext_experiments            -> experiments
    ext_experiment_ingredients -> experiment_ingredients
    ext_indicators             -> indicators
    ext_measurements           -> measurements
    ext_evidence               -> evidence

The downgrade restores the schema of all 19 tables and reverses every rename, so a
database stepped back to the previous revision matches what that revision's code expects --
including its foreign-key deletion policy, which the recreated tables carry inline rather
than leaving at the baseline's policy-free state. It does not restore data: the rows are
gone, and no promoter exists any more to rebuild them from the scientific tables.

Revision ID: c4e8f1a9d072
Revises: b7d4e9a2c1f3
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8f1a9d072"
down_revision: Union[str, None] = "b7d4e9a2c1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: Drop order: every table appears after everything that references it.
_DROP_ORDER: tuple[str, ...] = (
    "trajectory_observations",
    "model_predictions",
    "imputation_proposals",
    "lab_model_results",
    "model_fits",
    "model_runs",
    "trajectory_definitions",
    "lab_training_runs",
    "uploaded_datasets",
    "export_runs",
    "dataset_snapshots",
    "threshold_definitions",
    "normalization_mappings",
    "observations",
    "treatment_arms",
    "experiment_microorganisms",
    "experiments",
    "microorganisms",
    "studies",
)

#: (ext_ name, canonical name). Applied after the drops, so the target names are free.
_RENAMES: tuple[tuple[str, str], ...] = (
    ("ext_ingredients", "ingredients"),
    ("ext_experiments", "experiments"),
    ("ext_experiment_ingredients", "experiment_ingredients"),
    ("ext_indicators", "indicators"),
    ("ext_measurements", "measurements"),
    ("ext_evidence", "evidence"),
)

#: Indexes carried along by a table rename. Postgres renames neither indexes nor
#: constraints with their table, so without these the schema keeps `ix_ext_*` names that no
#: longer correspond to anything and that autogenerate would try to "fix" on every run.
_INDEX_RENAMES: tuple[tuple[str, str], ...] = (
    ("ix_ext_ingredients_id", "ix_ingredients_id"),
    ("ix_ext_ingredients_project_id", "ix_ingredients_project_id"),
    ("ix_ext_experiments_id", "ix_experiments_id"),
    ("ix_ext_experiments_paper_id", "ix_experiments_paper_id"),
    ("ix_ext_experiments_project_id", "ix_experiments_project_id"),
    ("ix_ext_indicators_id", "ix_indicators_id"),
    ("ix_ext_indicators_project_id", "ix_indicators_project_id"),
    ("ix_ext_evidence_id", "ix_evidence_id"),
    ("ix_ext_evidence_paper_id", "ix_evidence_paper_id"),
)

#: (table after rename, old constraint name, new constraint name). The unique constraints
#: are named in the models' `__table_args__`, so these two names are load-bearing.
_CONSTRAINT_RENAMES: tuple[tuple[str, str, str], ...] = (
    ("ingredients", "uq_ext_ing_proj_name", "uq_ingredient_project_name"),
    ("indicators", "uq_ext_ind_proj_type_unit", "uq_indicator_project_type_unit"),
    ("experiments", "fk_ext_experiments_job_id", "fk_experiments_job_id"),
)

#: Identity sequences behind the renamed tables' `id` columns. Nothing reads these by name --
#: Postgres resolves them through the column default, and Alembic recognises them as owned
#: SERIAL sequences either way -- but leaving `ext_evidence_id_seq` attached to `evidence`
#: is exactly the kind of half-renamed schema that makes the next person doubt which name
#: is current. The junction tables have none: their keys are composite.
_SEQUENCE_RENAMES: tuple[tuple[str, str], ...] = (
    ("ext_ingredients_id_seq", "ingredients_id_seq"),
    ("ext_experiments_id_seq", "experiments_id_seq"),
    ("ext_indicators_id_seq", "indicators_id_seq"),
    ("ext_evidence_id_seq", "evidence_id_seq"),
)


def _selected_model_constraint() -> str | None:
    """The FK on `model_runs.selected_model_id`, whatever it is currently called."""
    inspector = sa.inspect(op.get_bind())
    for fk in inspector.get_foreign_keys("model_runs"):
        if fk["constrained_columns"] == ["selected_model_id"] and fk.get("name"):
            return fk["name"]
    return None


def upgrade() -> None:
    # Break the model_runs <-> model_fits cycle first; neither table can be dropped while
    # the deferred constraint between them stands.
    cycle_fk = _selected_model_constraint()
    if cycle_fk:
        op.drop_constraint(cycle_fk, "model_runs", type_="foreignkey")

    for table in _DROP_ORDER:
        op.drop_table(table)

    for old, new in _RENAMES:
        op.rename_table(old, new)
    for old, new in _INDEX_RENAMES:
        op.execute(f"ALTER INDEX {old} RENAME TO {new}")
    for table, old, new in _CONSTRAINT_RENAMES:
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new}")
    for old, new in _SEQUENCE_RENAMES:
        op.execute(f"ALTER SEQUENCE {old} RENAME TO {new}")


def downgrade() -> None:
    # Reverse the renames first: the legacy `experiments` table cannot be recreated while
    # the scientific one still holds that name.
    for old, new in _SEQUENCE_RENAMES:
        op.execute(f"ALTER SEQUENCE {new} RENAME TO {old}")
    for table, old, new in _CONSTRAINT_RENAMES:
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {new} TO {old}")
    for old, new in _INDEX_RENAMES:
        op.execute(f"ALTER INDEX {new} RENAME TO {old}")
    for old, new in _RENAMES:
        op.rename_table(new, old)

    # Recreated in dependency order -- the reverse of the drop -- with the foreign-key
    # policy established by revision b7d4e9a2c1f3 baked in.
    op.create_table('microorganisms',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.Column('genus', sa.String(), nullable=False),
    sa.Column('species', sa.String(), nullable=True),
    sa.Column('strain', sa.String(), nullable=True),
    sa.Column('original_text', sa.String(), nullable=True),
    sa.Column('canonical_name', sa.String(), nullable=True),
    sa.Column('organism_role', sa.String(), nullable=True),
    sa.Column('gram_category', sa.String(), nullable=True),
    sa.Column('synonyms_json', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_microorganisms_project_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_microorganisms_id'), 'microorganisms', ['id'], unique=False)
    op.create_table('normalization_mappings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.Column('mapping_type', sa.String(), nullable=False),
    sa.Column('original_term', sa.String(), nullable=False),
    sa.Column('canonical_term', sa.String(), nullable=False),
    sa.Column('canonical_id', sa.Integer(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('source', sa.String(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('applied_count', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_normalization_mappings_created_by', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_normalization_mappings_project_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'mapping_type', 'original_term', name='uq_norm_mapping')
    )
    op.create_index(op.f('ix_normalization_mappings_id'), 'normalization_mappings', ['id'], unique=False)
    op.create_table('threshold_definitions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('measurement_type', sa.String(), nullable=False),
    sa.Column('threshold_value', sa.Float(), nullable=False),
    sa.Column('threshold_unit', sa.String(), nullable=True),
    sa.Column('comparison_operator', sa.String(), nullable=True),
    sa.Column('product_scope', sa.String(), nullable=True),
    sa.Column('microorganism_scope', sa.String(), nullable=True),
    sa.Column('source_type', sa.String(), nullable=True),
    sa.Column('source_citation', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_threshold_definitions_created_by', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_threshold_definitions_project_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_threshold_definitions_id'), 'threshold_definitions', ['id'], unique=False)
    op.create_table('dataset_snapshots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('label', sa.String(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('filters_json', sa.Text(), nullable=True),
    sa.Column('row_count', sa.Integer(), nullable=True),
    sa.Column('observation_count', sa.Integer(), nullable=True),
    sa.Column('includes_imputed', sa.Boolean(), nullable=True),
    sa.Column('only_approved', sa.Boolean(), nullable=True),
    sa.Column('feature_config_json', sa.Text(), nullable=True),
    sa.Column('snapshot_hash', sa.String(length=64), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_dataset_snapshots_created_by', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_dataset_snapshots_project_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dataset_snapshots_id'), 'dataset_snapshots', ['id'], unique=False)
    op.create_table('export_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('snapshot_id', sa.Integer(), nullable=True),
    sa.Column('format', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('file_path', sa.String(), nullable=True),
    sa.Column('file_size_bytes', sa.Integer(), nullable=True),
    sa.Column('filters_json', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_export_runs_created_by', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_export_runs_project_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], name='fk_export_runs_snapshot_id', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_export_runs_id'), 'export_runs', ['id'], unique=False)
    op.create_table('uploaded_datasets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('uploader_id', sa.Integer(), nullable=True),
    sa.Column('original_name', sa.String(), nullable=False),
    sa.Column('filename', sa.String(), nullable=False),
    sa.Column('file_path', sa.String(), nullable=False),
    sa.Column('file_hash', sa.String(length=64), nullable=True),
    sa.Column('sheet_name', sa.String(), nullable=True),
    sa.Column('dataset_family', sa.String(), nullable=True),
    sa.Column('row_count', sa.Integer(), nullable=True),
    sa.Column('col_count', sa.Integer(), nullable=True),
    sa.Column('headers_json', sa.Text(), nullable=True),
    sa.Column('column_types_json', sa.Text(), nullable=True),
    sa.Column('column_mapping_json', sa.Text(), nullable=True),
    sa.Column('parse_status', sa.String(), nullable=True),
    sa.Column('parse_error', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_uploaded_datasets_project_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploader_id'], ['users.id'], name='fk_uploaded_datasets_uploader_id', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_uploaded_datasets_file_hash'), 'uploaded_datasets', ['file_hash'], unique=False)
    op.create_index(op.f('ix_uploaded_datasets_id'), 'uploaded_datasets', ['id'], unique=False)
    op.create_index(op.f('ix_uploaded_datasets_project_id'), 'uploaded_datasets', ['project_id'], unique=False)
    op.create_table('lab_training_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=True),
    sa.Column('dataset_family', sa.String(), nullable=False),
    sa.Column('column_mapping_json', sa.Text(), nullable=True),
    sa.Column('dataset_hash', sa.String(length=64), nullable=True),
    sa.Column('n_trajectories', sa.Integer(), nullable=True),
    sa.Column('n_fitted', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_lab_training_runs_created_by', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['dataset_id'], ['uploaded_datasets.id'], name='fk_lab_training_runs_dataset_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name='fk_lab_training_runs_job_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_lab_training_runs_project_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lab_training_runs_id'), 'lab_training_runs', ['id'], unique=False)
    op.create_index(op.f('ix_lab_training_runs_job_id'), 'lab_training_runs', ['job_id'], unique=False)
    op.create_index(op.f('ix_lab_training_runs_project_id'), 'lab_training_runs', ['project_id'], unique=False)
    op.create_table('lab_model_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('training_run_id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('model_name', sa.String(), nullable=False),
    sa.Column('model_family', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('skip_reason', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('results_json', sa.Text(), nullable=True),
    sa.Column('metrics_json', sa.Text(), nullable=True),
    sa.Column('parameters_json', sa.Text(), nullable=True),
    sa.Column('artifact_path', sa.String(), nullable=True),
    sa.Column('preprocessing_path', sa.String(), nullable=True),
    sa.Column('feature_cols_json', sa.Text(), nullable=True),
    sa.Column('target_col', sa.String(), nullable=True),
    sa.Column('event_col', sa.String(), nullable=True),
    sa.Column('mae', sa.Float(), nullable=True),
    sa.Column('rmse', sa.Float(), nullable=True),
    sa.Column('r_squared', sa.Float(), nullable=True),
    sa.Column('concordance_index', sa.Float(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_lab_model_results_project_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['training_run_id'], ['lab_training_runs.id'], name='fk_lab_model_results_training_run_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lab_model_results_id'), 'lab_model_results', ['id'], unique=False)
    op.create_index(op.f('ix_lab_model_results_project_id'), 'lab_model_results', ['project_id'], unique=False)
    op.create_index(op.f('ix_lab_model_results_training_run_id'), 'lab_model_results', ['training_run_id'], unique=False)
    op.create_table('studies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('paper_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('authors_json', sa.Text(), nullable=True),
    sa.Column('publication_year', sa.Integer(), nullable=True),
    sa.Column('journal', sa.String(), nullable=True),
    sa.Column('doi_original', sa.String(), nullable=True),
    sa.Column('doi_normalized', sa.String(), nullable=True),
    sa.Column('country', sa.String(), nullable=True),
    sa.Column('study_type', sa.String(), nullable=True),
    sa.Column('abstract', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('review_status', sa.String(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_studies_created_by', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], name='fk_studies_paper_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_studies_project_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='fk_studies_updated_by', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_studies_doi_normalized'), 'studies', ['doi_normalized'], unique=False)
    op.create_index(op.f('ix_studies_id'), 'studies', ['id'], unique=False)
    op.create_index('ix_study_project_doi', 'studies', ['project_id', 'doi_normalized'], unique=False)
    op.create_table('experiments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('study_id', sa.Integer(), nullable=False),
    sa.Column('experiment_label', sa.String(), nullable=True),
    sa.Column('food_category', sa.String(), nullable=True),
    sa.Column('product_name_original', sa.String(), nullable=True),
    sa.Column('product_name_normalized', sa.String(), nullable=True),
    sa.Column('product_family', sa.String(), nullable=True),
    sa.Column('matrix_description', sa.Text(), nullable=True),
    sa.Column('milk_species', sa.String(), nullable=True),
    sa.Column('milk_treatment', sa.String(), nullable=True),
    sa.Column('fat_content_class', sa.String(), nullable=True),
    sa.Column('sampling_location', sa.String(), nullable=True),
    sa.Column('storage_temperature_value', sa.Float(), nullable=True),
    sa.Column('storage_temperature_unit_original', sa.String(), nullable=True),
    sa.Column('storage_temperature_c', sa.Float(), nullable=True),
    sa.Column('storage_relative_humidity', sa.Float(), nullable=True),
    sa.Column('packaging_type', sa.String(), nullable=True),
    sa.Column('atmosphere_type', sa.String(), nullable=True),
    sa.Column('gas_composition_json', sa.Text(), nullable=True),
    sa.Column('light_condition', sa.String(), nullable=True),
    sa.Column('storage_duration_value', sa.Float(), nullable=True),
    sa.Column('storage_duration_unit_original', sa.String(), nullable=True),
    sa.Column('storage_duration_days', sa.Float(), nullable=True),
    sa.Column('study_design', sa.String(), nullable=True),
    sa.Column('replicate_design', sa.String(), nullable=True),
    sa.Column('artificial_inoculation', sa.Boolean(), nullable=True),
    sa.Column('initial_ph', sa.Float(), nullable=True),
    sa.Column('initial_water_activity', sa.Float(), nullable=True),
    sa.Column('initial_salt_pct', sa.Float(), nullable=True),
    sa.Column('initial_moisture_pct', sa.Float(), nullable=True),
    sa.Column('extra_conditions_json', sa.Text(), nullable=True),
    sa.Column('condition_signature', sa.String(), nullable=True),
    sa.Column('review_status', sa.String(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_experiments_created_by', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['study_id'], ['studies.id'], name='fk_experiments_study_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='fk_experiments_updated_by', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_experiments_condition_signature'), 'experiments', ['condition_signature'], unique=False)
    op.create_index(op.f('ix_experiments_id'), 'experiments', ['id'], unique=False)
    op.create_table('experiment_microorganisms',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('experiment_id', sa.Integer(), nullable=False),
    sa.Column('microorganism_id', sa.Integer(), nullable=False),
    sa.Column('role_in_study', sa.String(), nullable=True),
    sa.Column('inoculum_level', sa.Float(), nullable=True),
    sa.Column('inoculum_unit', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['experiment_id'], ['experiments.id'], name='fk_experiment_microorganisms_experiment_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['microorganism_id'], ['microorganisms.id'], name='fk_experiment_microorganisms_microorganism_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('experiment_id', 'microorganism_id', name='uq_exp_micro')
    )
    op.create_index(op.f('ix_experiment_microorganisms_id'), 'experiment_microorganisms', ['id'], unique=False)
    op.create_table('treatment_arms',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('experiment_id', sa.Integer(), nullable=False),
    sa.Column('arm_label', sa.String(), nullable=True),
    sa.Column('is_control', sa.Boolean(), nullable=True),
    sa.Column('control_arm_id', sa.Integer(), nullable=True),
    sa.Column('treatment_type', sa.String(), nullable=True),
    sa.Column('ingredient_name_original', sa.String(), nullable=True),
    sa.Column('ingredient_name_normalized', sa.String(), nullable=True),
    sa.Column('ingredient_source', sa.String(), nullable=True),
    sa.Column('ingredient_family', sa.String(), nullable=True),
    sa.Column('concentration_value_original', sa.Float(), nullable=True),
    sa.Column('concentration_unit_original', sa.String(), nullable=True),
    sa.Column('concentration_value_normalized', sa.Float(), nullable=True),
    sa.Column('concentration_unit_normalized', sa.String(), nullable=True),
    sa.Column('application_method', sa.String(), nullable=True),
    sa.Column('treatment_timing', sa.String(), nullable=True),
    sa.Column('combination_treatments_json', sa.Text(), nullable=True),
    sa.Column('extra_treatment_json', sa.Text(), nullable=True),
    sa.Column('review_status', sa.String(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['control_arm_id'], ['treatment_arms.id'], name='fk_treatment_arms_control_arm_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_treatment_arms_created_by', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['experiment_id'], ['experiments.id'], name='fk_treatment_arms_experiment_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_treatment_arms_id'), 'treatment_arms', ['id'], unique=False)
    op.create_table('observations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('treatment_arm_id', sa.Integer(), nullable=False),
    sa.Column('microorganism_id', sa.Integer(), nullable=True),
    sa.Column('measurement_type', sa.String(), nullable=False),
    sa.Column('measurement_subtype', sa.String(), nullable=True),
    sa.Column('measurement_unit_normalized', sa.String(), nullable=True),
    sa.Column('time_value_original', sa.Float(), nullable=True),
    sa.Column('time_unit_original', sa.String(), nullable=True),
    sa.Column('time_days', sa.Float(), nullable=True),
    sa.Column('value_original_text', sa.String(), nullable=True),
    sa.Column('numeric_value_original', sa.Float(), nullable=True),
    sa.Column('unit_original', sa.String(), nullable=True),
    sa.Column('numeric_value_normalized', sa.Float(), nullable=True),
    sa.Column('unit_normalized', sa.String(), nullable=True),
    sa.Column('mean_value', sa.Float(), nullable=True),
    sa.Column('standard_deviation', sa.Float(), nullable=True),
    sa.Column('standard_error', sa.Float(), nullable=True),
    sa.Column('minimum_value', sa.Float(), nullable=True),
    sa.Column('maximum_value', sa.Float(), nullable=True),
    sa.Column('replicate_count', sa.Integer(), nullable=True),
    sa.Column('detection_limit', sa.Float(), nullable=True),
    sa.Column('detection_limit_unit', sa.String(), nullable=True),
    sa.Column('censoring_type', sa.String(), nullable=True),
    sa.Column('value_origin', sa.String(), nullable=True),
    sa.Column('missing_reason', sa.String(), nullable=True),
    sa.Column('is_imputed', sa.Boolean(), nullable=True),
    sa.Column('is_derived', sa.Boolean(), nullable=True),
    sa.Column('significance_letter', sa.String(), nullable=True),
    sa.Column('quality_score', sa.Float(), nullable=True),
    sa.Column('review_status', sa.String(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('extraction_run_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_observations_created_by', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['extraction_run_id'], ['extraction_runs.id'], name='fk_observations_extraction_run_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['microorganism_id'], ['microorganisms.id'], name='fk_observations_microorganism_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['treatment_arm_id'], ['treatment_arms.id'], name='fk_observations_treatment_arm_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='fk_observations_updated_by', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_obs_arm_time', 'observations', ['treatment_arm_id', 'time_days'], unique=False)
    op.create_index('ix_obs_type', 'observations', ['measurement_type'], unique=False)
    op.create_index(op.f('ix_observations_id'), 'observations', ['id'], unique=False)
    op.create_table('trajectory_definitions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('experiment_id', sa.Integer(), nullable=True),
    sa.Column('treatment_arm_id', sa.Integer(), nullable=True),
    sa.Column('label', sa.String(), nullable=True),
    sa.Column('measurement_type', sa.String(), nullable=False),
    sa.Column('measurement_subtype', sa.String(), nullable=True),
    sa.Column('microorganism_id', sa.Integer(), nullable=True),
    sa.Column('process_class', sa.String(), nullable=True),
    sa.Column('grouping_signature', sa.String(), nullable=True),
    sa.Column('n_points', sa.Integer(), nullable=True),
    sa.Column('time_min_days', sa.Float(), nullable=True),
    sa.Column('time_max_days', sa.Float(), nullable=True),
    sa.Column('has_control', sa.Boolean(), nullable=True),
    sa.Column('data_sufficient', sa.Boolean(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_trajectory_definitions_created_by', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['experiment_id'], ['experiments.id'], name='fk_trajectory_definitions_experiment_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['microorganism_id'], ['microorganisms.id'], name='fk_trajectory_definitions_microorganism_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_trajectory_definitions_project_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['treatment_arm_id'], ['treatment_arms.id'], name='fk_trajectory_definitions_treatment_arm_id', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trajectory_definitions_grouping_signature'), 'trajectory_definitions', ['grouping_signature'], unique=False)
    op.create_index(op.f('ix_trajectory_definitions_id'), 'trajectory_definitions', ['id'], unique=False)
    op.create_table('model_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trajectory_id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('models_tried', sa.Integer(), nullable=True),
    sa.Column('models_converged', sa.Integer(), nullable=True),
    sa.Column('selected_model_id', sa.Integer(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_model_runs_created_by', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_model_runs_project_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['selected_model_id'], ['model_fits.id'], name='fk_model_runs_selected_model_id', ondelete='SET NULL', use_alter=True),
    sa.ForeignKeyConstraint(['trajectory_id'], ['trajectory_definitions.id'], name='fk_model_runs_trajectory_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_model_runs_id'), 'model_runs', ['id'], unique=False)
    op.create_table('model_fits',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('model_name', sa.String(), nullable=False),
    sa.Column('model_version', sa.String(), nullable=True),
    sa.Column('process_class', sa.String(), nullable=True),
    sa.Column('converged', sa.Boolean(), nullable=True),
    sa.Column('convergence_message', sa.String(), nullable=True),
    sa.Column('parameters_json', sa.Text(), nullable=True),
    sa.Column('parameter_bounds_json', sa.Text(), nullable=True),
    sa.Column('parameter_se_json', sa.Text(), nullable=True),
    sa.Column('mae', sa.Float(), nullable=True),
    sa.Column('rmse', sa.Float(), nullable=True),
    sa.Column('r_squared', sa.Float(), nullable=True),
    sa.Column('adjusted_r_squared', sa.Float(), nullable=True),
    sa.Column('aic', sa.Float(), nullable=True),
    sa.Column('bic', sa.Float(), nullable=True),
    sa.Column('aicc', sa.Float(), nullable=True),
    sa.Column('residual_bias', sa.Float(), nullable=True),
    sa.Column('loo_mae', sa.Float(), nullable=True),
    sa.Column('loo_rmse', sa.Float(), nullable=True),
    sa.Column('biological_violations', sa.Integer(), nullable=True),
    sa.Column('applicability_status', sa.String(), nullable=True),
    sa.Column('applicability_reasons_json', sa.Text(), nullable=True),
    sa.Column('rank', sa.Integer(), nullable=True),
    sa.Column('equation_text', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['model_runs.id'], name='fk_model_fits_run_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_model_fits_id'), 'model_fits', ['id'], unique=False)
    op.create_table('model_predictions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fit_id', sa.Integer(), nullable=False),
    sa.Column('time_days', sa.Float(), nullable=False),
    sa.Column('predicted_value', sa.Float(), nullable=True),
    sa.Column('lower_bound', sa.Float(), nullable=True),
    sa.Column('upper_bound', sa.Float(), nullable=True),
    sa.Column('interval_type', sa.String(), nullable=True),
    sa.Column('interval_level', sa.Float(), nullable=True),
    sa.Column('is_interpolation', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['fit_id'], ['model_fits.id'], name='fk_model_predictions_fit_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_model_predictions_id'), 'model_predictions', ['id'], unique=False)
    op.create_table('trajectory_observations',
    sa.Column('trajectory_id', sa.Integer(), nullable=False),
    sa.Column('observation_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['observation_id'], ['observations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['trajectory_id'], ['trajectory_definitions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('trajectory_id', 'observation_id')
    )
    op.create_table('imputation_proposals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('trajectory_id', sa.Integer(), nullable=True),
    sa.Column('fit_id', sa.Integer(), nullable=True),
    sa.Column('target_observation_id', sa.Integer(), nullable=True),
    sa.Column('target_arm_id', sa.Integer(), nullable=True),
    sa.Column('target_time_days', sa.Float(), nullable=True),
    sa.Column('target_measurement_type', sa.String(), nullable=True),
    sa.Column('predicted_value', sa.Float(), nullable=True),
    sa.Column('lower_bound', sa.Float(), nullable=True),
    sa.Column('upper_bound', sa.Float(), nullable=True),
    sa.Column('interval_type', sa.String(), nullable=True),
    sa.Column('is_interpolation', sa.Boolean(), nullable=True),
    sa.Column('extrapolation_days', sa.Float(), nullable=True),
    sa.Column('applicability_status', sa.String(), nullable=True),
    sa.Column('applicability_reasons_json', sa.Text(), nullable=True),
    sa.Column('cross_validation_mae', sa.Float(), nullable=True),
    sa.Column('cross_validation_rmse', sa.Float(), nullable=True),
    sa.Column('n_points_used', sa.Integer(), nullable=True),
    sa.Column('model_name', sa.String(), nullable=True),
    sa.Column('parameters_json', sa.Text(), nullable=True),
    sa.Column('reviewer_decision', sa.String(), nullable=True),
    sa.Column('reviewer_id', sa.Integer(), nullable=True),
    sa.Column('reviewer_note', sa.Text(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_imputation_proposals_created_by', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['fit_id'], ['model_fits.id'], name='fk_imputation_proposals_fit_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_imputation_proposals_project_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], name='fk_imputation_proposals_reviewer_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['target_arm_id'], ['treatment_arms.id'], name='fk_imputation_proposals_target_arm_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['target_observation_id'], ['observations.id'], name='fk_imputation_proposals_target_observation_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['trajectory_id'], ['trajectory_definitions.id'], name='fk_imputation_proposals_trajectory_id', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_imputation_proposals_id'), 'imputation_proposals', ['id'], unique=False)
