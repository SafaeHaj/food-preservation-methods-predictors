"""
Export service — builds the full 23-sheet Excel workbook, CSV zip, JSON, Parquet.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

EXPORT_DIR = Path(os.environ.get("EXPORT_DIR", "./exports"))


def _ensure_export_dir() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return EXPORT_DIR


def build_export_async(run_id: int) -> None:
    """Background task: build export file for a given ExportRun."""
    from app.db.database import SessionLocal
    from app.db.models import ExportRun

    db: Session = SessionLocal()
    try:
        run = db.query(ExportRun).filter(ExportRun.id == run_id).first()
        if not run:
            return
        run.status = "building"
        db.commit()

        try:
            if run.format == "excel":
                path = _build_excel(run.project_id, run_id, db)
            elif run.format == "csv_zip":
                path = _build_csv_zip(run.project_id, run_id, db)
            elif run.format == "json":
                path = _build_json(run.project_id, run_id, db)
            elif run.format == "parquet":
                path = _build_parquet(run.project_id, run_id, db)
            else:
                raise ValueError(f"Unknown format: {run.format}")

            run.file_path = str(path)
            run.file_size_bytes = path.stat().st_size
            run.status = "completed"
            run.completed_at = datetime.utcnow()
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.utcnow()

        db.commit()
    finally:
        db.close()


def _collect_dataframes(project_id: int, db: "Session") -> dict[str, Any]:
    """Collect all project data as dict of DataFrames."""
    import pandas as pd
    from app.db.models import (
        Study, Experiment, TreatmentArm, Observation,
        Microorganism, ExperimentMicroorganism,
        ProvenanceRecord, ValidationIssue, AuditEvent,
        ModelRun, ModelFit, ModelPrediction, ImputationProposal,
        TrajectoryDefinition, ThresholdDefinition,
        NormalizationMapping, Job, ExtractionRun,
    )

    studies = db.query(Study).filter(Study.project_id == project_id).all()
    study_ids = [s.id for s in studies]

    experiments = (db.query(Experiment)
                     .filter(Experiment.study_id.in_(study_ids))
                     .all()) if study_ids else []
    exp_ids = [e.id for e in experiments]

    arms = (db.query(TreatmentArm)
              .filter(TreatmentArm.experiment_id.in_(exp_ids))
              .all()) if exp_ids else []
    arm_ids = [a.id for a in arms]

    observations = (db.query(Observation)
                      .filter(Observation.treatment_arm_id.in_(arm_ids))
                      .all()) if arm_ids else []

    def rows(objs, exclude=None):
        exclude = exclude or set()
        result = []
        for o in objs:
            row = {}
            for c in o.__table__.columns:
                if c.name not in exclude:
                    row[c.name] = getattr(o, c.name)
            result.append(row)
        return result

    dfs = {}
    dfs["studies"] = pd.DataFrame(rows(studies))
    dfs["experiments"] = pd.DataFrame(rows(experiments))
    dfs["treatment_arms"] = pd.DataFrame(rows(arms))
    dfs["observations"] = pd.DataFrame(rows(observations))

    # Microorganisms
    micro_ids = set()
    if exp_ids:
        exp_micros = (db.query(ExperimentMicroorganism)
                        .filter(ExperimentMicroorganism.experiment_id.in_(exp_ids))
                        .all())
        dfs["experiment_microorganisms"] = pd.DataFrame(rows(exp_micros))
        micro_ids = {em.microorganism_id for em in exp_micros}

    if micro_ids:
        micros = db.query(Microorganism).filter(Microorganism.id.in_(micro_ids)).all()
        dfs["microorganisms"] = pd.DataFrame(rows(micros))

    # Trajectories & models
    trajs = (db.query(TrajectoryDefinition)
               .filter(TrajectoryDefinition.project_id == project_id)
               .all())
    dfs["trajectories"] = pd.DataFrame(rows(trajs))

    traj_ids = [t.id for t in trajs]
    if traj_ids:
        model_runs = db.query(ModelRun).filter(ModelRun.trajectory_id.in_(traj_ids)).all()
        dfs["model_runs"] = pd.DataFrame(rows(model_runs))
        run_ids = [r.id for r in model_runs]
        if run_ids:
            fits = db.query(ModelFit).filter(ModelFit.run_id.in_(run_ids)).all()
            dfs["model_fits"] = pd.DataFrame(rows(fits))

    # Imputations
    imps = (db.query(ImputationProposal)
              .filter(ImputationProposal.project_id == project_id)
              .all())
    dfs["imputations"] = pd.DataFrame(rows(imps))

    # Thresholds
    thresh = (db.query(ThresholdDefinition)
                .filter(ThresholdDefinition.project_id == project_id)
                .all())
    dfs["thresholds"] = pd.DataFrame(rows(thresh))

    # Audit
    obs_ids = [o.id for o in observations]
    audit = (db.query(AuditEvent)
               .filter(AuditEvent.project_id == project_id)
               .order_by(AuditEvent.created_at)
               .limit(10000)
               .all())
    dfs["audit_log"] = pd.DataFrame(rows(audit))

    return dfs


def _build_excel(project_id: int, run_id: int, db: "Session") -> Path:
    import pandas as pd

    dfs = _collect_dataframes(project_id, db)
    out_dir = _ensure_export_dir()
    path = out_dir / f"export_{project_id}_{run_id}.xlsx"

    with pd.ExcelWriter(str(path), engine="openpyxl") as writer:
        for sheet_name, df in dfs.items():
            if not df.empty:
                # Truncate sheet name to Excel's 31-char limit
                df.to_excel(writer, sheet_name=sheet_name[:31], index=False)

    return path


def _build_csv_zip(project_id: int, run_id: int, db: "Session") -> Path:
    import pandas as pd
    import zipfile

    dfs = _collect_dataframes(project_id, db)
    out_dir = _ensure_export_dir()
    path = out_dir / f"export_{project_id}_{run_id}.zip"

    with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as zf:
        for name, df in dfs.items():
            if not df.empty:
                zf.writestr(f"{name}.csv", df.to_csv(index=False))

    return path


def _build_json(project_id: int, run_id: int, db: "Session") -> Path:
    import pandas as pd

    dfs = _collect_dataframes(project_id, db)
    out_dir = _ensure_export_dir()
    path = out_dir / f"export_{project_id}_{run_id}.json"

    payload = {}
    for name, df in dfs.items():
        if not df.empty:
            payload[name] = json.loads(df.to_json(orient="records", date_format="iso"))

    with open(str(path), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    return path


def _build_parquet(project_id: int, run_id: int, db: "Session") -> Path:
    import zipfile
    import pandas as pd

    dfs = _collect_dataframes(project_id, db)
    out_dir = _ensure_export_dir()
    path = out_dir / f"export_{project_id}_{run_id}_parquet.zip"

    with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as zf:
        for name, df in dfs.items():
            if not df.empty:
                import io
                buf = io.BytesIO()
                df.to_parquet(buf, index=False, engine="pyarrow")
                zf.writestr(f"{name}.parquet", buf.getvalue())

    return path
