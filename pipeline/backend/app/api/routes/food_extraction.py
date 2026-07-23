"""
food_extraction.py — API routes for the new food-safety extraction pipeline.

Routes:
  POST   /api/projects/{project_id}/food-extract/{paper_id}  Trigger extraction
  GET    /api/projects/{project_id}/food-experiments          List experiments
  GET    /api/projects/{project_id}/food-experiments/{exp_id} Single experiment + full detail
  GET    /api/projects/{project_id}/ingredients               Ingredient catalogue
  GET    /api/projects/{project_id}/indicators                Indicator catalogue
  GET    /api/projects/{project_id}/food-experiments/{exp_id}/measurements
  GET    /api/evidence/{evidence_id}                          Evidence record
  GET    /api/evidence/{evidence_id}/image                    Full-size evidence crop PNG
  GET    /api/evidence/{evidence_id}/thumbnail                Thumbnail PNG
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import UPLOAD_PATH
from app.db.database import SessionLocal, get_db
from app.db.models import (
    ExtEvidence, ExtExperiment, ExtExperimentIngredient,
    ExtIndicator, ExtIngredient, ExtMeasurement,
    Job, Paper, Project, User,
)
from app.services.docling_extractor import extract_pdf
from app.services.chart_converter import convert_charts
from app.services.evidence_package import build_packages
from app.services.food_extractor import extract_food_data
from app.services.evidence_capture import save_evidence_crop

logger = logging.getLogger(__name__)

router = APIRouter(tags=["food-extraction"])

EVIDENCE_BASE = UPLOAD_PATH / "evidence"


# ─── DB helpers ────────────────────────────────────────────────────────────────

def _get_or_create_ingredient(db: Session, project_id: int, name: str, func_class: str, source: str) -> ExtIngredient:
    ing = db.query(ExtIngredient).filter(
        ExtIngredient.project_id == project_id,
        ExtIngredient.ingredient_name == name,
    ).first()
    if not ing:
        ing = ExtIngredient(
            project_id=project_id,
            ingredient_name=name,
            functional_class=func_class,
            source=source,
        )
        db.add(ing)
        db.flush()
    return ing


def _get_or_create_indicator(
    db: Session, project_id: int,
    ind_type: str, ind_unit: str, threshold: Optional[float],
) -> ExtIndicator:
    ind = db.query(ExtIndicator).filter(
        ExtIndicator.project_id == project_id,
        ExtIndicator.indicator_type == ind_type,
        ExtIndicator.indicator_unit == ind_unit,
    ).first()
    if not ind:
        ind = ExtIndicator(
            project_id=project_id,
            indicator_type=ind_type,
            indicator_unit=ind_unit,
            indicator_threshold=threshold,
        )
        db.add(ind)
        db.flush()
    elif threshold is not None and ind.indicator_threshold is None:
        ind.indicator_threshold = threshold
    return ind


def _save_evidence(
    db: Session,
    paper_id: int,
    pdf_path: str,
    entity_type: str,
    entity_key: dict,
    field_name: Optional[str],
    ev: dict,
    ref_to_bbox: Optional[dict] = None,
    chart_item_refs: Optional[set] = None,
) -> ExtEvidence:
    # Prefer docling_item_ref bbox; fall back to legacy bounding_box field
    item_ref = ev.get("docling_item_ref")
    bbox = {}
    if ref_to_bbox and item_ref and item_ref in ref_to_bbox:
        bbox = ref_to_bbox[item_ref] or {}
    else:
        bbox = ev.get("bounding_box") or {}

    is_chart = (
        ev.get("source_type") == "chart_csv"
        or bool(ev.get("value_is_approximate", False))
        or (chart_item_refs is not None and item_ref in (chart_item_refs or set()))
    )

    rec = ExtEvidence(
        paper_id=paper_id,
        entity_type=entity_type,
        entity_key=json.dumps(entity_key),
        field_name=field_name,
        page_number=ev.get("page_number"),
        source_type=ev.get("source_type", "text"),
        source_label=ev.get("source_label"),
        exact_text=ev.get("exact_text"),
        bbox_x1=bbox.get("x1"),
        bbox_y1=bbox.get("y1"),
        bbox_x2=bbox.get("x2"),
        bbox_y2=bbox.get("y2"),
        confidence=ev.get("confidence"),
        figure_series=ev.get("figure_series"),
        x_axis_value=ev.get("x_axis_value"),
        y_axis_value=ev.get("y_axis_value"),
        value_is_approximate=bool(ev.get("value_is_approximate", False)),
        docling_item_ref=item_ref,
        is_chart_derived=is_chart,
    )
    db.add(rec)
    db.flush()

    # Generate evidence image crop if we have page + bbox
    page_num = ev.get("page_number")
    if page_num and bbox.get("x1") is not None:
        img_dir = EVIDENCE_BASE / str(paper_id)
        img_path = img_dir / f"ev_{rec.id}.png"
        thumb_path = img_dir / f"thumb_{rec.id}.png"
        ok = save_evidence_crop(pdf_path, page_num, bbox, img_path, thumb_path)
        if ok:
            rec.evidence_image_path = str(img_path)
            rec.evidence_thumbnail_path = str(thumb_path)

    return rec


# ─── Background extraction task ────────────────────────────────────────────────

def _run_food_extraction(paper_id: int, project_id: int, job_id: int) -> None:
    """
    Full Docling pipeline:
      1. Docling PDF extraction (text / tables / figures + provenance)
      2. PP-Chart2Table chart→CSV conversion + validation
      3. Evidence package assembly (keyword-filtered, token-budgeted)
      4. LLM extraction (Pass 1) + optional Pass 2 verification
      5. DB persist with evidence anchoring
    """
    db = SessionLocal()
    try:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        job   = db.query(Job).filter(Job.id == job_id).first()
        if not paper or not job:
            return

        paper.status = "extracting"
        job.status   = "running"
        job.started_at = datetime.utcnow()
        job.current_step = "Extracting PDF structure with Docling"
        db.commit()

        # ── Step 1: Docling extraction ─────────────────────────────────────────
        docling_result = extract_pdf(paper.file_path)
        paper.page_count = docling_result.page_count
        job.progress = 20
        job.current_step = f"Converting {len(docling_result.figures)} figures with PP-Chart2Table"
        db.commit()

        # ── Step 2: Chart conversion ───────────────────────────────────────────
        chart_results = convert_charts(docling_result.figures, docling_result.cache_dir)
        job.progress = 35
        job.current_step = "Building evidence packages"
        db.commit()

        # ── Step 3: Evidence packages ──────────────────────────────────────────
        packages = build_packages(docling_result, chart_results)
        known_refs = docling_result.known_item_refs

        # Build bbox lookup: item_ref → {x1,y1,x2,y2} for evidence image crops
        ref_to_bbox: dict = {}
        for t in docling_result.texts:
            if t.bbox:
                ref_to_bbox[t.item_ref] = t.bbox
        for t in docling_result.tables:
            if t.bbox:
                ref_to_bbox[t.item_ref] = t.bbox
        for f in docling_result.figures:
            if f.bbox:
                ref_to_bbox[f.item_ref] = f.bbox

        chart_item_refs = {cr.item_ref for cr in chart_results if cr.status == "valid"}

        if not packages:
            # No relevant evidence found — mark complete with 0 experiments
            paper.status = "extracted"
            job.status = "completed"
            job.progress = 100
            job.current_step = "Done — no relevant experimental evidence found"
            job.completed_at = datetime.utcnow()
            job.result_json = json.dumps({"experiments": 0, "measurements": 0,
                                          "reasoning": "No relevant evidence found.", "low_confidence_count": 0})
            db.commit()
            return

        job.progress = 45
        job.current_step = f"Running LLM extraction on {len(packages)} evidence packages"
        db.commit()

        # ── Step 4: LLM extraction ─────────────────────────────────────────────
        result = extract_food_data(
            evidence_packages=packages,
            known_item_refs=known_refs,
            enable_verification=True,
        )
        experiments_data = result.get("experiments", [])
        job.progress = 75
        job.current_step = f"Saving {len(experiments_data)} experiments to database"
        db.commit()

        # ── Step 5: Persist to DB ──────────────────────────────────────────────
        exp_count = 0
        meas_count = 0

        for exp_dict in experiments_data:
            meat_matrix = exp_dict.get("meat_matrix") or ""
            treatment   = exp_dict.get("treatment") or ""
            if not meat_matrix or not treatment:
                continue

            exp_row = ExtExperiment(
                project_id=project_id,
                paper_id=paper_id,
                job_id=job_id,
                meat_matrix=meat_matrix,
                treatment=treatment,
            )
            db.add(exp_row)
            db.flush()
            exp_count += 1

            # Experiment-level evidence
            for ev in exp_dict.get("experiment_evidence", []):
                _save_evidence(
                    db, paper_id, paper.file_path,
                    "experiment", {"experiment_id": exp_row.id},
                    None, ev, ref_to_bbox, chart_item_refs,
                )

            # ── Ingredients ───────────────────────────────────────────────────
            for ing_dict in exp_dict.get("ingredients", []):
                name = ing_dict.get("ingredient_name") or ""
                if not name:
                    continue
                conc = ing_dict.get("concentration")
                conc_unit = ing_dict.get("concentration_unit") or ""
                if conc is None:
                    continue

                ing_row = _get_or_create_ingredient(
                    db, project_id,
                    name=name,
                    func_class=ing_dict.get("functional_class", "unknown"),
                    source=ing_dict.get("source", ""),
                )

                # Junction row (upsert)
                junction = db.query(ExtExperimentIngredient).filter(
                    ExtExperimentIngredient.experiment_id == exp_row.id,
                    ExtExperimentIngredient.ingredient_id == ing_row.id,
                ).first()
                if not junction:
                    junction = ExtExperimentIngredient(
                        experiment_id=exp_row.id,
                        ingredient_id=ing_row.id,
                        concentration=float(conc),
                        concentration_unit=conc_unit,
                    )
                    db.add(junction)
                    db.flush()

                # Ingredient-link evidence
                for ev in ing_dict.get("evidence", []):
                    _save_evidence(
                        db, paper_id, paper.file_path,
                        "ingredient_link",
                        {"experiment_id": exp_row.id, "ingredient_id": ing_row.id},
                        None, ev, ref_to_bbox, chart_item_refs,
                    )

            # ── Measurements ──────────────────────────────────────────────────
            for meas_dict in exp_dict.get("measurements", []):
                day      = meas_dict.get("day")
                val      = meas_dict.get("indicator_value")
                ind_type = meas_dict.get("indicator_type") or ""
                ind_unit = meas_dict.get("indicator_unit") or ""
                if day is None or val is None or not ind_type:
                    continue

                ind_row = _get_or_create_indicator(
                    db, project_id,
                    ind_type=ind_type,
                    ind_unit=ind_unit,
                    threshold=meas_dict.get("indicator_threshold"),
                )

                # Duplicate guard on (experiment, day, indicator)
                existing = db.query(ExtMeasurement).filter(
                    ExtMeasurement.experiment_id == exp_row.id,
                    ExtMeasurement.day == int(day),
                    ExtMeasurement.indicator_id == ind_row.id,
                ).first()
                if not existing:
                    meas_row = ExtMeasurement(
                        experiment_id=exp_row.id,
                        day=int(day),
                        indicator_id=ind_row.id,
                        indicator_value=float(val),
                        value_is_approximate=bool(meas_dict.get("value_is_approximate", False)),
                    )
                    db.add(meas_row)
                    db.flush()
                    meas_count += 1

                    # Measurement evidence
                    for ev in meas_dict.get("evidence", []):
                        _save_evidence(
                            db, paper_id, paper.file_path,
                            "measurement",
                            {"experiment_id": exp_row.id, "day": int(day), "indicator_id": ind_row.id},
                            "indicator_value", ev, ref_to_bbox, chart_item_refs,
                        )

        paper.status = "extracted"
        job.status   = "completed"
        job.progress = 100
        job.current_step = (
            f"Done — {exp_count} experiments, {meas_count} measurements"
        )
        job.completed_at = datetime.utcnow()
        job.result_json  = json.dumps({
            "experiments": exp_count,
            "measurements": meas_count,
            "reasoning": result.get("reasoning_summary", ""),
            "low_confidence_count": result.get("low_confidence_count", 0),
        })
        db.commit()

    except Exception as exc:
        logger.exception("Food extraction failed for paper %d", paper_id)
        try:
            paper = db.query(Paper).filter(Paper.id == paper_id).first()
            job   = db.query(Job).filter(Job.id == job_id).first()
            if paper:
                paper.status = "error"
                paper.error_message = str(exc)[:500]
            if job:
                job.status = "failed"
                job.error_message = str(exc)[:500]
                job.completed_at = datetime.utcnow()
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ─── Trigger endpoint ──────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/food-extract/{paper_id}", status_code=202)
def trigger_food_extraction(
    project_id: int,
    paper_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    paper = db.query(Paper).filter(Paper.id == paper_id, Paper.project_id == project_id).first()
    if not paper:
        raise HTTPException(404, "Paper not found")
    if paper.status == "extracting":
        raise HTTPException(409, "Extraction already in progress for this paper")

    job = Job(
        project_id=project_id,
        paper_id=paper_id,
        job_type="food_extraction",
        status="queued",
        created_by=user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_run_food_extraction, paper_id, project_id, job.id)
    return {
        "message": "Food extraction started",
        "paper_id": paper_id,
        "job_id": job.id,
        "pipeline": "docling → pp-chart2table → evidence-packages → llama-3.3-70b (2-pass)",
    }


# ─── Read endpoints ────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/food-experiments")
def list_food_experiments(
    project_id: int,
    paper_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    q = db.query(ExtExperiment).filter(ExtExperiment.project_id == project_id)
    if paper_id:
        q = q.filter(ExtExperiment.paper_id == paper_id)
    exps = q.order_by(ExtExperiment.id.desc()).all()

    results = []
    for exp in exps:
        # Ingredient summary
        ings = (
            db.query(ExtIngredient, ExtExperimentIngredient)
            .join(ExtExperimentIngredient, ExtIngredient.id == ExtExperimentIngredient.ingredient_id)
            .filter(ExtExperimentIngredient.experiment_id == exp.id)
            .all()
        )
        ing_list = [
            {
                "ingredient_id": ing.id,
                "ingredient_name": ing.ingredient_name,
                "functional_class": ing.functional_class,
                "source": ing.source,
                "concentration": junc.concentration,
                "concentration_unit": junc.concentration_unit,
            }
            for ing, junc in ings
        ]
        # Measurement count
        meas_count = db.query(ExtMeasurement).filter(ExtMeasurement.experiment_id == exp.id).count()
        results.append({
            "id": exp.id,
            "paper_id": exp.paper_id,
            "meat_matrix": exp.meat_matrix,
            "treatment": exp.treatment,
            "ingredients": ing_list,
            "measurement_count": meas_count,
            "created_at": exp.created_at.isoformat() if exp.created_at else None,
        })
    return results


@router.get("/projects/{project_id}/food-experiments/{exp_id}")
def get_food_experiment(
    project_id: int,
    exp_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    exp = db.query(ExtExperiment).filter(
        ExtExperiment.id == exp_id, ExtExperiment.project_id == project_id
    ).first()
    if not exp:
        raise HTTPException(404, "Experiment not found")

    # Ingredients with junction data
    ings = (
        db.query(ExtIngredient, ExtExperimentIngredient)
        .join(ExtExperimentIngredient, ExtIngredient.id == ExtExperimentIngredient.ingredient_id)
        .filter(ExtExperimentIngredient.experiment_id == exp_id)
        .all()
    )
    # Measurements with indicator details
    meas_rows = (
        db.query(ExtMeasurement, ExtIndicator)
        .join(ExtIndicator, ExtMeasurement.indicator_id == ExtIndicator.id)
        .filter(ExtMeasurement.experiment_id == exp_id)
        .order_by(ExtMeasurement.day, ExtIndicator.indicator_type)
        .all()
    )
    # Evidence
    evidence = db.query(ExtEvidence).filter(
        ExtEvidence.entity_key.contains(f'"experiment_id": {exp_id}') |
        ExtEvidence.entity_key.contains(f'"experiment_id":{exp_id}')
    ).all()

    return {
        "id": exp.id,
        "paper_id": exp.paper_id,
        "meat_matrix": exp.meat_matrix,
        "treatment": exp.treatment,
        "created_at": exp.created_at.isoformat() if exp.created_at else None,
        "ingredients": [
            {
                "ingredient_id": ing.id,
                "ingredient_name": ing.ingredient_name,
                "functional_class": ing.functional_class,
                "source": ing.source,
                "concentration": junc.concentration,
                "concentration_unit": junc.concentration_unit,
            }
            for ing, junc in ings
        ],
        "measurements": [
            {
                "day": m.day,
                "indicator_id": ind.id,
                "indicator_type": ind.indicator_type,
                "indicator_unit": ind.indicator_unit,
                "indicator_threshold": ind.indicator_threshold,
                "indicator_value": m.indicator_value,
                "value_is_approximate": m.value_is_approximate,
            }
            for m, ind in meas_rows
        ],
        "evidence": [_evidence_out(e) for e in evidence],
    }


@router.get("/projects/{project_id}/food-experiments/{exp_id}/measurements")
def list_measurements(
    project_id: int,
    exp_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    rows = (
        db.query(ExtMeasurement, ExtIndicator)
        .join(ExtIndicator, ExtMeasurement.indicator_id == ExtIndicator.id)
        .filter(ExtMeasurement.experiment_id == exp_id)
        .order_by(ExtMeasurement.day, ExtIndicator.indicator_type)
        .all()
    )
    return [
        {
            "day": m.day,
            "indicator_id": ind.id,
            "indicator_type": ind.indicator_type,
            "indicator_unit": ind.indicator_unit,
            "indicator_threshold": ind.indicator_threshold,
            "indicator_value": m.indicator_value,
            "value_is_approximate": m.value_is_approximate,
        }
        for m, ind in rows
    ]


@router.get("/projects/{project_id}/ingredients")
def list_ingredients(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    ings = db.query(ExtIngredient).filter(
        ExtIngredient.project_id == project_id
    ).order_by(ExtIngredient.ingredient_name).all()
    return [
        {
            "id": i.id,
            "ingredient_name": i.ingredient_name,
            "functional_class": i.functional_class,
            "source": i.source,
        }
        for i in ings
    ]


@router.get("/projects/{project_id}/indicators")
def list_indicators(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    inds = db.query(ExtIndicator).filter(
        ExtIndicator.project_id == project_id
    ).order_by(ExtIndicator.indicator_type).all()
    return [
        {
            "id": i.id,
            "indicator_type": i.indicator_type,
            "indicator_unit": i.indicator_unit,
            "indicator_threshold": i.indicator_threshold,
        }
        for i in inds
    ]


# ─── Evidence endpoints ────────────────────────────────────────────────────────

def _evidence_out(e: ExtEvidence) -> dict:
    return {
        "id": e.id,
        "entity_type": e.entity_type,
        "entity_key": json.loads(e.entity_key) if e.entity_key else {},
        "field_name": e.field_name,
        "page_number": e.page_number,
        "source_type": e.source_type,
        "source_label": e.source_label,
        "exact_text": e.exact_text,
        "bounding_box": {
            "x1": e.bbox_x1, "y1": e.bbox_y1,
            "x2": e.bbox_x2, "y2": e.bbox_y2,
        } if e.bbox_x1 is not None else None,
        "confidence": e.confidence,
        "figure_series": e.figure_series,
        "x_axis_value": e.x_axis_value,
        "y_axis_value": e.y_axis_value,
        "value_is_approximate": e.value_is_approximate,
        "has_image": e.evidence_image_path is not None,
        "has_thumbnail": e.evidence_thumbnail_path is not None,
    }


@router.get("/evidence/{evidence_id}")
def get_evidence(
    evidence_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ev = db.query(ExtEvidence).filter(ExtEvidence.id == evidence_id).first()
    if not ev:
        raise HTTPException(404, "Evidence record not found")
    return _evidence_out(ev)


@router.get("/evidence/{evidence_id}/image")
def get_evidence_image(
    evidence_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ev = db.query(ExtEvidence).filter(ExtEvidence.id == evidence_id).first()
    if not ev or not ev.evidence_image_path:
        raise HTTPException(404, "Evidence image not available")
    path = Path(ev.evidence_image_path)
    if not path.exists():
        raise HTTPException(404, "Evidence image file not found on disk")
    return FileResponse(str(path), media_type="image/png")


@router.get("/evidence/{evidence_id}/thumbnail")
def get_evidence_thumbnail(
    evidence_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ev = db.query(ExtEvidence).filter(ExtEvidence.id == evidence_id).first()
    if not ev or not ev.evidence_thumbnail_path:
        raise HTTPException(404, "Thumbnail not available")
    path = Path(ev.evidence_thumbnail_path)
    if not path.exists():
        raise HTTPException(404, "Thumbnail file not found on disk")
    return FileResponse(str(path), media_type="image/png")
