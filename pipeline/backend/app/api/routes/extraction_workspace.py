"""
extraction_workspace.py — Extraction Workspace API.

Progressive PDF analysis pipeline (Docling → context linking → chart conversion → scoring).
Decoupled from the LLM extraction step so users can review all evidence before sending to Llama 4.

Routes:
  POST   /projects/{pid}/papers/{paper_id}/workspace            Start extraction job
  GET    /projects/{pid}/papers/{paper_id}/workspace/status     Poll job progress
  GET    /projects/{pid}/papers/{paper_id}/assets               List all assets
  GET    /projects/{pid}/papers/{paper_id}/assets/{id}          Asset detail + context links
  GET    /projects/{pid}/papers/{paper_id}/assets/{id}/image    Serve figure PNG
  GET    /projects/{pid}/papers/{paper_id}/assets/{id}/page-image  Serve full page PNG
  GET    /projects/{pid}/papers/{paper_id}/assets/{id}/csv      Download chart CSV
  PATCH  /projects/{pid}/papers/{paper_id}/assets/{id}          Update selection / classification
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import SessionLocal, get_db
from app.db.models import (
    AssetContextLink, ExtractionAsset, ExtExperiment, ExtExperimentIngredient,
    ExtIngredient, ExtIndicator, ExtMeasurement,
    Job, Paper, Project, User,
)
from app.services.asset_classifier import classify_figure, score_relevance
from app.services.chart_converter import convert_charts
from app.services.context_linker import build_context_links
from app.services.docling_extractor import extract_pdf
from app.services.evidence_package import EvidenceItem, EvidencePackage
from app.services.food_extractor import extract_food_data

logger = logging.getLogger(__name__)
router = APIRouter(tags=["extraction-workspace"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _require_project(project_id: int, user: User, db: Session) -> Project:
    proj = db.query(Project).filter(
        Project.id == project_id,
        Project.owner_id == user.id,
    ).first()
    if not proj:
        raise HTTPException(404, "Project not found")
    return proj


def _get_paper(project_id: int, paper_id: int, db: Session) -> Paper:
    paper = db.query(Paper).filter(
        Paper.id == paper_id,
        Paper.project_id == project_id,
    ).first()
    if not paper:
        raise HTTPException(404, "Paper not found")
    return paper


def _asset_out(asset: ExtractionAsset) -> dict:
    return {
        "id": asset.id,
        "paper_id": asset.paper_id,
        "project_id": asset.project_id,
        "docling_item_ref": asset.docling_item_ref,
        "asset_type": asset.asset_type,
        "page_number": asset.page_number,
        "bbox": json.loads(asset.bbox_json) if asset.bbox_json else None,
        "section_name": asset.section_name,
        "caption": asset.caption,
        "has_image": bool(asset.image_path and Path(asset.image_path).exists()),
        "has_page_image": bool(asset.page_image_path and Path(asset.page_image_path).exists()),
        "has_csv": bool(asset.csv_path and Path(asset.csv_path).exists()),
        "csv_rows": asset.csv_rows,
        "csv_cols": asset.csv_cols,
        "classification": asset.classification,
        "conversion_status": asset.conversion_status,
        "conversion_error": asset.conversion_error,
        "relevance_score": asset.relevance_score,
        "selected_for_llm": asset.selected_for_llm,
        "user_note": asset.user_note,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


def _count_csv_rows(csv_path: Optional[str]) -> Optional[int]:
    if not csv_path or not Path(csv_path).exists():
        return None
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            return max(0, sum(1 for _ in f) - 1)
    except Exception:
        return None


def _count_csv_cols(csv_path: Optional[str]) -> Optional[int]:
    if not csv_path or not Path(csv_path).exists():
        return None
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            header = f.readline()
            return len(header.split(","))
    except Exception:
        return None


def _generate_page_images(pdf_path: str, pages_dir: Path) -> dict:
    """Render all pages as PNG using PyMuPDF. Returns {page_num: path_str}."""
    result: dict = {}
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        zoom = 1.5  # ~108 DPI — readable without being huge
        mat = fitz.Matrix(zoom, zoom)
        for i in range(len(doc)):
            page_num = i + 1
            img_path = pages_dir / f"page_{page_num:04d}.png"
            if not img_path.exists():
                pix = doc.load_page(i).get_pixmap(matrix=mat, alpha=False)
                pix.save(str(img_path))
            result[page_num] = str(img_path)
        doc.close()
    except Exception as exc:
        logger.warning("Page image generation failed: %s", exc)
    return result


def _write_manifest(cache_dir: Path, assets: list) -> None:
    manifest_path = cache_dir / "item_manifest.jsonl"
    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            for asset in assets:
                entry = {
                    "id": asset.id,
                    "item_ref": asset.docling_item_ref,
                    "type": asset.asset_type,
                    "page_number": asset.page_number,
                    "bbox": json.loads(asset.bbox_json) if asset.bbox_json else None,
                    "section": asset.section_name,
                    "caption": asset.caption,
                    "image_path": asset.image_path,
                    "csv_path": asset.csv_path,
                    "classification": asset.classification,
                    "relevance_score": asset.relevance_score,
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Manifest write failed: %s", exc)


# ─── Background extraction task ───────────────────────────────────────────────

def _run_workspace_extraction(paper_id: int, project_id: int, job_id: int) -> None:
    """
    Full workspace extraction pipeline:
      1. Docling PDF → texts / tables / figures
      2. Page image generation
      3. Save all assets to DB
      4. Deterministic context linking
      5. PP-Chart2Table chart conversion (if available)
      6. Relevance scoring
      7. Write item_manifest.jsonl
    """
    db = SessionLocal()
    try:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        job   = db.query(Job).filter(Job.id == job_id).first()
        if not paper or not job:
            return

        paper.status  = "extracting"
        job.status    = "running"
        job.started_at = datetime.utcnow()
        job.current_step = "Parsing document structure with Docling"
        job.progress  = 5
        db.commit()

        # ── Step 1: Docling extraction ────────────────────────────────────────
        try:
            docling_result = extract_pdf(paper.file_path)
        except ImportError as exc:
            job.status        = "failed"
            job.error_message = f"Docling not installed: {exc}"
            paper.status      = "failed"
            paper.error_message = str(exc)
            db.commit()
            return
        except Exception as exc:
            job.status        = "failed"
            job.error_message = str(exc)
            paper.status      = "failed"
            paper.error_message = str(exc)
            db.commit()
            return

        paper.page_count = docling_result.page_count
        job.progress  = 25
        job.current_step = (
            f"Generating page images for {docling_result.page_count} pages"
        )
        db.commit()

        # ── Step 2: Page images ───────────────────────────────────────────────
        cache_dir  = Path(docling_result.cache_dir)
        pages_dir  = cache_dir / "pages"
        pages_dir.mkdir(exist_ok=True)
        page_image_paths = _generate_page_images(paper.file_path, pages_dir)

        job.progress  = 35
        job.current_step = (
            f"Saving {len(docling_result.figures)} figures, "
            f"{len(docling_result.tables)} tables to workspace"
        )
        db.commit()

        # ── Step 3: Save assets to DB (delete stale first) ───────────────────
        db.query(ExtractionAsset).filter(
            ExtractionAsset.paper_id == paper_id
        ).delete(synchronize_session=False)
        db.commit()

        asset_map: dict = {}  # item_ref → asset_id

        for i, fig in enumerate(docling_result.figures):
            page_img = page_image_paths.get(fig.page_number)
            asset = ExtractionAsset(
                paper_id         = paper_id,
                project_id       = project_id,
                job_id           = job_id,
                docling_item_ref = fig.item_ref,
                asset_type       = "figure",
                page_number      = fig.page_number,
                bbox_json        = json.dumps(fig.bbox) if fig.bbox else None,
                caption          = fig.caption,
                image_path       = fig.image_path or None,
                page_image_path  = page_img,
                classification   = "unknown",
                conversion_status = "pending" if fig.image_path else "skipped",
                relevance_score  = 0.0,
                selected_for_llm = False,
            )
            db.add(asset)
            db.flush()
            asset_map[fig.item_ref] = asset.id

        for i, tbl in enumerate(docling_result.tables):
            page_img  = page_image_paths.get(tbl.page_number)
            csv_rows  = _count_csv_rows(tbl.csv_path)
            csv_cols  = _count_csv_cols(tbl.csv_path)
            asset = ExtractionAsset(
                paper_id         = paper_id,
                project_id       = project_id,
                job_id           = job_id,
                docling_item_ref = tbl.item_ref,
                asset_type       = "native_table",
                page_number      = tbl.page_number,
                bbox_json        = json.dumps(tbl.bbox) if tbl.bbox else None,
                caption          = tbl.caption,
                csv_path         = tbl.csv_path,
                page_image_path  = page_img,
                classification   = "native_table",
                conversion_status = "not_applicable",
                csv_rows         = csv_rows,
                csv_cols         = csv_cols,
                relevance_score  = 0.0,
                selected_for_llm = False,
            )
            db.add(asset)
            db.flush()
            asset_map[tbl.item_ref] = asset.id

        db.commit()

        job.progress  = 50
        job.current_step = "Linking context to visual elements"
        db.commit()

        # ── Step 4: Context linking ───────────────────────────────────────────
        for i, fig in enumerate(docling_result.figures):
            aid = asset_map.get(fig.item_ref)
            if not aid:
                continue
            for link_data in build_context_links(
                docling_result, fig.item_ref, "figure",
                fig.page_number, fig.caption, i,
            ):
                db.add(AssetContextLink(asset_id=aid, **link_data))

        for i, tbl in enumerate(docling_result.tables):
            aid = asset_map.get(tbl.item_ref)
            if not aid:
                continue
            for link_data in build_context_links(
                docling_result, tbl.item_ref, "native_table",
                tbl.page_number, tbl.caption, i,
            ):
                db.add(AssetContextLink(asset_id=aid, **link_data))

        db.commit()

        job.progress  = 65
        job.current_step = (
            f"Converting {len(docling_result.figures)} figures with PP-Chart2Table"
        )
        db.commit()

        # ── Step 5: Chart conversion ──────────────────────────────────────────
        chart_results = convert_charts(docling_result.figures, docling_result.cache_dir)
        cr_map = {cr.item_ref: cr for cr in chart_results}

        for fig in docling_result.figures:
            aid = asset_map.get(fig.item_ref)
            if not aid:
                continue
            asset = db.query(ExtractionAsset).filter(ExtractionAsset.id == aid).first()
            if not asset:
                continue
            cr = cr_map.get(fig.item_ref)
            if cr:
                if cr.status == "valid":
                    asset.conversion_status = "complete"
                    asset.csv_path  = cr.csv_path
                    asset.csv_rows  = cr.row_count
                    asset.csv_cols  = cr.col_count
                elif cr.status == "rejected":
                    asset.conversion_status = "not_a_chart"
                elif cr.status == "error":
                    asset.conversion_status = "failed"
                    asset.conversion_error  = cr.reject_reason
                else:
                    asset.conversion_status = "skipped"
            else:
                asset.conversion_status = "skipped"

            asset.classification = classify_figure(
                asset.image_path, asset.csv_path, asset.csv_rows, asset.csv_cols,
                asset.caption, asset.conversion_status,
                page_number=asset.page_number, item_ref=asset.docling_item_ref,
            )

        db.commit()

        job.progress  = 85
        job.current_step = "Scoring scientific relevance"
        db.commit()

        # ── Step 6: Relevance scoring ─────────────────────────────────────────
        all_assets = db.query(ExtractionAsset).filter(
            ExtractionAsset.paper_id == paper_id
        ).all()

        for asset in all_assets:
            ctx_texts = [lnk.text for lnk in asset.context_links[:10]]
            asset.relevance_score = score_relevance(
                asset.caption, asset.section_name, ctx_texts, asset.asset_type,
                classification=asset.classification,
                page_number=asset.page_number,
                item_ref=asset.docling_item_ref,
            )

        db.commit()

        # ── Step 7: Write manifest ────────────────────────────────────────────
        _write_manifest(cache_dir, all_assets)

        n_fig = sum(1 for a in all_assets if a.asset_type == "figure")
        n_tbl = sum(1 for a in all_assets if a.asset_type == "native_table")
        n_chart = sum(1 for a in all_assets if a.classification == "chart")
        n_skipped_charts = sum(
            1 for a in all_assets
            if a.asset_type == "figure" and a.conversion_status == "skipped"
        )
        n_logos = sum(
            1 for a in all_assets
            if a.classification in ("publisher_logo", "license_icon", "decorative_asset")
        )

        # Build a stage-specific completion message — never say "Complete" if PP was skipped
        from app.services.chart_converter import _chart_model_error
        pp_available = _chart_model_error is None
        if n_fig == 0:
            chart_status = "no figures"
        elif pp_available and n_chart > 0:
            chart_status = f"{n_chart} charts converted"
        elif pp_available and n_chart == 0:
            chart_status = "0 charts (no chart figures found)"
        else:
            chart_status = f"chart conversion unavailable (PaddleOCR not installed)"

        step_summary = (
            f"Docling completed — {n_fig} figures, {n_tbl} tables · "
            f"Chart stage: {chart_status}"
        )
        if n_logos:
            step_summary += f" · {n_logos} decorative/logo assets excluded"

        paper.status  = "extracted"
        job.status    = "completed"
        job.progress  = 100
        job.current_step = step_summary
        job.completed_at = datetime.utcnow()
        job.result_json  = json.dumps({
            "figures": n_fig,
            "charts": n_chart,
            "native_tables": n_tbl,
            "texts": len(docling_result.texts),
            "total_assets": len(all_assets),
            "page_count": docling_result.page_count,
            "chart_conversion_available": pp_available,
            "skipped_charts": n_skipped_charts,
            "decorative_excluded": n_logos,
        })
        db.commit()

    except Exception as exc:
        logger.error(
            "Workspace extraction failed for paper %d: %s", paper_id, exc, exc_info=True
        )
        try:
            paper = db.query(Paper).filter(Paper.id == paper_id).first()
            job   = db.query(Job).filter(Job.id == job_id).first()
            if paper:
                paper.status = "failed"
                paper.error_message = str(exc)
            if job:
                job.status = "failed"
                job.error_message = str(exc)[:500]
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/papers/{paper_id}/workspace", status_code=202)
def start_workspace(
    project_id: int,
    paper_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Start (or restart) the workspace extraction for one paper."""
    _require_project(project_id, user, db)
    paper = _get_paper(project_id, paper_id, db)

    # If already running, return the existing job
    running = db.query(Job).filter(
        Job.paper_id == paper_id,
        Job.job_type == "workspace_extraction",
        Job.status.in_(["queued", "running"]),
    ).first()
    if running:
        return {"job_id": running.id, "status": "already_running"}

    job = Job(
        project_id   = project_id,
        paper_id     = paper_id,
        job_type     = "workspace_extraction",
        status       = "queued",
        current_step = "Queued",
        progress     = 0,
        created_by   = user.id,
    )
    db.add(job)
    db.flush()
    job_id = job.id
    db.commit()

    background_tasks.add_task(_run_workspace_extraction, paper_id, project_id, job_id)
    return {"job_id": job_id, "status": "queued", "paper": {"id": paper.id, "filename": paper.original_name}}


@router.get("/projects/{project_id}/papers/{paper_id}/workspace/status")
def workspace_status(
    project_id: int,
    paper_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Poll extraction job status for one paper."""
    _require_project(project_id, user, db)
    _get_paper(project_id, paper_id, db)

    job = (
        db.query(Job)
        .filter(Job.paper_id == paper_id, Job.job_type == "workspace_extraction")
        .order_by(Job.id.desc())
        .first()
    )

    asset_count = db.query(ExtractionAsset).filter(
        ExtractionAsset.paper_id == paper_id
    ).count()

    if not job:
        return {
            "status": "not_started",
            "progress": 0,
            "current_step": "",
            "asset_count": asset_count,
            "job_id": None,
        }

    return {
        "status": job.status,
        "progress": job.progress or 0,
        "current_step": job.current_step or "",
        "asset_count": asset_count,
        "job_id": job.id,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error": job.error_message or None,
        "result": json.loads(job.result_json) if job.result_json and job.result_json != "{}" else None,
    }


@router.get("/projects/{project_id}/papers/{paper_id}/assets")
def list_assets(
    project_id: int,
    paper_id: int,
    asset_type: Optional[str] = None,
    classification: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all extraction assets for a paper, optionally filtered by type."""
    _require_project(project_id, user, db)
    _get_paper(project_id, paper_id, db)

    q = db.query(ExtractionAsset).filter(ExtractionAsset.paper_id == paper_id)
    if asset_type:
        q = q.filter(ExtractionAsset.asset_type == asset_type)
    if classification:
        q = q.filter(ExtractionAsset.classification == classification)

    total = q.count()
    assets = (
        q.order_by(ExtractionAsset.page_number, ExtractionAsset.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {"total": total, "items": [_asset_out(a) for a in assets]}


@router.get("/projects/{project_id}/papers/{paper_id}/assets/{asset_id}")
def get_asset(
    project_id: int,
    paper_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return a single asset with all context links."""
    _require_project(project_id, user, db)
    _get_paper(project_id, paper_id, db)

    asset = db.query(ExtractionAsset).filter(
        ExtractionAsset.id == asset_id,
        ExtractionAsset.paper_id == paper_id,
    ).first()
    if not asset:
        raise HTTPException(404, "Asset not found")

    return {
        **_asset_out(asset),
        "context_links": [
            {
                "link_type": lnk.link_type,
                "text": lnk.text,
                "item_ref": lnk.item_ref,
                "page_number": lnk.page_number,
                "score": lnk.score,
            }
            for lnk in sorted(asset.context_links, key=lambda l: -l.score)
        ],
    }


@router.get("/chart2table/health")
def chart2table_health():
    """Report whether PP-Chart2Table is available in this process."""
    from app.services.chart_converter import _chart_model, _chart_model_error, _get_chart_model
    import torch
    model = _chart_model  # don't force-load here — just report current state
    available = model is not None
    device = "unknown"
    if available:
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            pass
    return {
        "available": available,
        "model_loaded": available,
        "device": device if available else None,
        "model_name": "PP-Chart2Table" if available else None,
        "last_error": _chart_model_error,
    }


@router.get("/projects/{project_id}/assets")
def list_project_assets(
    project_id: int,
    asset_type: Optional[str] = None,
    classification: Optional[str] = None,
    skip: int = 0,
    limit: int = 500,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all extraction assets across all papers in a project."""
    q = db.query(ExtractionAsset).filter(ExtractionAsset.project_id == project_id)
    if asset_type:
        q = q.filter(ExtractionAsset.asset_type == asset_type)
    if classification:
        q = q.filter(ExtractionAsset.classification == classification)

    total = q.count()
    assets = (
        q.order_by(ExtractionAsset.paper_id, ExtractionAsset.page_number, ExtractionAsset.id)
        .offset(skip)
        .limit(limit)
        .all()
    )

    paper_ids = list({a.paper_id for a in assets})
    papers = {p.id: p for p in db.query(Paper).filter(Paper.id.in_(paper_ids)).all()} if paper_ids else {}

    def _out(a: ExtractionAsset) -> dict:
        paper = papers.get(a.paper_id)
        return {**_asset_out(a), "paper_name": paper.original_name if paper else None}

    return {"total": total, "items": [_out(a) for a in assets]}


@router.get("/projects/{project_id}/papers/{paper_id}/assets/{asset_id}/image")
def get_asset_image(
    project_id: int,
    paper_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
):
    asset = db.query(ExtractionAsset).filter(
        ExtractionAsset.id == asset_id,
        ExtractionAsset.paper_id == paper_id,
        ExtractionAsset.project_id == project_id,
    ).first()
    if not asset or not asset.image_path:
        raise HTTPException(404, "Image not found")
    p = Path(asset.image_path)
    if not p.exists():
        raise HTTPException(404, "Image file missing from disk")
    return FileResponse(str(p), media_type="image/png",
                        headers={"Cache-Control": "max-age=3600"})


@router.get("/projects/{project_id}/papers/{paper_id}/assets/{asset_id}/page-image")
def get_page_image(
    project_id: int,
    paper_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
):
    asset = db.query(ExtractionAsset).filter(
        ExtractionAsset.id == asset_id,
        ExtractionAsset.paper_id == paper_id,
        ExtractionAsset.project_id == project_id,
    ).first()
    if not asset or not asset.page_image_path:
        raise HTTPException(404, "Page image not found")
    p = Path(asset.page_image_path)
    if not p.exists():
        raise HTTPException(404, "Page image file missing from disk")
    return FileResponse(str(p), media_type="image/png",
                        headers={"Cache-Control": "max-age=3600"})


@router.get("/projects/{project_id}/papers/{paper_id}/assets/{asset_id}/csv")
def get_asset_csv(
    project_id: int,
    paper_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
):
    asset = db.query(ExtractionAsset).filter(
        ExtractionAsset.id == asset_id,
        ExtractionAsset.paper_id == paper_id,
        ExtractionAsset.project_id == project_id,
    ).first()
    if not asset or not asset.csv_path:
        raise HTTPException(404, "CSV not available for this asset")
    p = Path(asset.csv_path)
    if not p.exists():
        raise HTTPException(404, "CSV file missing from disk")
    return FileResponse(
        str(p),
        media_type="text/csv",
        filename=f"asset_{asset_id}.csv",
    )


@router.patch("/projects/{project_id}/papers/{paper_id}/assets/{asset_id}")
def update_asset(
    project_id: int,
    paper_id: int,
    asset_id: int,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update asset classification, LLM selection flag, or user note."""
    _require_project(project_id, user, db)
    asset = db.query(ExtractionAsset).filter(
        ExtractionAsset.id == asset_id,
        ExtractionAsset.paper_id == paper_id,
    ).first()
    if not asset:
        raise HTTPException(404, "Asset not found")

    if "selected_for_llm" in data:
        asset.selected_for_llm = bool(data["selected_for_llm"])
    if "classification" in data:
        asset.classification = str(data["classification"])
    if "user_note" in data:
        asset.user_note = str(data["user_note"]) if data["user_note"] is not None else None

    db.commit()
    return _asset_out(asset)


# ─── LLM Validation endpoints ─────────────────────────────────────────────────

def _build_packages_from_db_assets(
    assets: list,
    db: Session,
    max_tokens: int = 3000,
) -> tuple:
    """
    Build EvidencePackage objects from ExtractionAsset DB records without re-running Docling.
    Returns (packages, known_item_refs).
    """
    MAX_CHARS = max_tokens * 4
    items: list = []
    known_refs: set = set()

    for asset in assets:
        if asset.docling_item_ref:
            known_refs.add(asset.docling_item_ref)

        links = sorted(asset.context_links, key=lambda l: -(l.score or 0))

        # Native table with CSV → table evidence
        if asset.asset_type == "native_table" and asset.csv_path and Path(asset.csv_path).exists():
            try:
                content = Path(asset.csv_path).read_text(encoding="utf-8")[:4000]
                if content.strip():
                    items.append(EvidenceItem(
                        item_ref=asset.docling_item_ref or f"asset_{asset.id}",
                        page_number=asset.page_number or 0,
                        source_type="table",
                        source_label=asset.caption or f"Table (page {asset.page_number})",
                        caption=asset.caption,
                        content=content,
                        bbox=json.loads(asset.bbox_json) if asset.bbox_json else None,
                        is_approximate=False,
                    ))
            except Exception:
                pass

        # Figure/chart with CSV → chart_csv evidence
        elif asset.asset_type == "figure" and asset.csv_path and Path(asset.csv_path).exists():
            try:
                content = Path(asset.csv_path).read_text(encoding="utf-8")[:2000]
                if content.strip():
                    items.append(EvidenceItem(
                        item_ref=asset.docling_item_ref or f"asset_{asset.id}",
                        page_number=asset.page_number or 0,
                        source_type="chart_csv",
                        source_label=asset.caption or f"Figure (page {asset.page_number})",
                        caption=asset.caption,
                        content=content,
                        bbox=json.loads(asset.bbox_json) if asset.bbox_json else None,
                        is_approximate=True,
                    ))
            except Exception:
                pass

        # Context link text paragraphs
        for link in links:
            if link.link_type in ("neighbor_before", "neighbor_after", "keyword_match",
                                   "same_section", "explicit_figure_reference"):
                ref = link.item_ref or asset.docling_item_ref or f"link_{link.id}"
                items.append(EvidenceItem(
                    item_ref=ref,
                    page_number=link.page_number or asset.page_number or 0,
                    source_type="text",
                    source_label=asset.section_name or link.link_type,
                    caption=None,
                    content=link.text[:1500],
                    bbox=None,
                    is_approximate=False,
                ))

    if not items:
        return [], known_refs

    # Split into token-budget packages
    packages: list = []
    current_items: list = []
    current_chars = 0
    pkg_idx = 1

    for item in items:
        item_chars = len(item.content) + len(item.item_ref) + 100
        if current_items and current_chars + item_chars > MAX_CHARS:
            packages.append(EvidencePackage(
                index=pkg_idx,
                items=current_items,
                token_estimate=current_chars // 4,
            ))
            pkg_idx += 1
            current_items = []
            current_chars = 0
        current_items.append(item)
        current_chars += item_chars

    if current_items:
        packages.append(EvidencePackage(
            index=pkg_idx,
            items=current_items,
            token_estimate=current_chars // 4,
        ))

    return packages, known_refs


def _run_llm_validation(paper_id: int, project_id: int, job_id: int) -> None:
    """
    LLM extraction using pre-extracted workspace assets.
    Skips Docling — reads ExtractionAsset + AssetContextLink from DB directly.
    """
    db = SessionLocal()
    try:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        job   = db.query(Job).filter(Job.id == job_id).first()
        if not paper or not job:
            return

        job.status = "running"
        job.started_at = datetime.utcnow()
        job.current_step = "Loading selected workspace assets"
        job.progress = 5
        db.commit()

        # Load all assets and apply same auto-proposal logic as evidence-packages.
        # Explicitly selected always included; decorative always excluded;
        # high-relevance tables/charts auto-included.
        _NON_SCI = frozenset({"publisher_logo", "license_icon", "decorative_asset"})
        _AUTO_SCORE = 3.0
        _AUTO_TABLE_SCORE = 1.0

        all_paper_assets = db.query(ExtractionAsset).filter(
            ExtractionAsset.paper_id == paper_id,
        ).all()

        selected = []
        for a in all_paper_assets:
            if a.classification in _NON_SCI:
                continue
            if a.selected_for_llm:
                selected.append(a)
                continue
            # Auto-include rule
            if a.asset_type == "native_table" and a.relevance_score >= _AUTO_TABLE_SCORE:
                selected.append(a)
            elif a.classification == "chart" and a.csv_path and Path(a.csv_path).exists():
                selected.append(a)
            elif a.relevance_score >= _AUTO_SCORE:
                selected.append(a)

        # Last resort: use everything non-decorative
        if not selected:
            selected = [a for a in all_paper_assets if a.classification not in _NON_SCI]

        job.progress = 15
        job.current_step = f"Building evidence packages from {len(selected)} assets"
        db.commit()

        packages, known_refs = _build_packages_from_db_assets(selected, db)

        if not packages:
            job.status = "completed"
            job.progress = 100
            job.current_step = "Done — no relevant evidence found in selected assets"
            job.completed_at = datetime.utcnow()
            job.result_json = json.dumps({
                "experiments": 0, "measurements": 0,
                "reasoning": "No relevant evidence found in the selected assets.",
                "low_confidence_count": 0,
            })
            db.commit()
            return

        job.progress = 30
        job.current_step = f"Sending {len(packages)} package(s) to Llama 4 via Groq"
        db.commit()

        result = extract_food_data(
            evidence_packages=packages,
            known_item_refs=known_refs,
            enable_verification=True,
        )

        experiments_data = result.get("experiments", [])
        job.progress = 75
        job.current_step = f"Persisting {len(experiments_data)} experiment(s) to database"
        db.commit()

        # ── Helpers (local, same logic as food_extraction.py) ─────────────────

        def _get_ing(name: str, func_class: str, source: str) -> ExtIngredient:
            ing = db.query(ExtIngredient).filter(
                ExtIngredient.project_id == project_id,
                ExtIngredient.ingredient_name == name,
            ).first()
            if not ing:
                ing = ExtIngredient(
                    project_id=project_id, ingredient_name=name,
                    functional_class=func_class, source=source,
                )
                db.add(ing)
                db.flush()
            return ing

        def _get_ind(ind_type: str, ind_unit: str, threshold: Optional[float]) -> ExtIndicator:
            ind = db.query(ExtIndicator).filter(
                ExtIndicator.project_id == project_id,
                ExtIndicator.indicator_type == ind_type,
                ExtIndicator.indicator_unit == ind_unit,
            ).first()
            if not ind:
                ind = ExtIndicator(
                    project_id=project_id, indicator_type=ind_type,
                    indicator_unit=ind_unit, indicator_threshold=threshold,
                )
                db.add(ind)
                db.flush()
            elif threshold is not None and ind.indicator_threshold is None:
                ind.indicator_threshold = threshold
            return ind

        # ── Persist results ───────────────────────────────────────────────────

        exp_count = meas_count = 0

        for exp_dict in experiments_data:
            meat_matrix = exp_dict.get("meat_matrix") or ""
            treatment   = exp_dict.get("treatment") or ""
            if not meat_matrix or not treatment:
                continue

            exp_row = ExtExperiment(
                project_id=project_id, paper_id=paper_id, job_id=job_id,
                meat_matrix=meat_matrix, treatment=treatment,
            )
            db.add(exp_row)
            db.flush()
            exp_count += 1

            for ing_dict in exp_dict.get("ingredients", []):
                name = ing_dict.get("ingredient_name") or ""
                conc = ing_dict.get("concentration")
                if not name or conc is None:
                    continue
                ing_row = _get_ing(
                    name=name,
                    func_class=ing_dict.get("functional_class", "unknown"),
                    source=ing_dict.get("source", ""),
                )
                junction = db.query(ExtExperimentIngredient).filter(
                    ExtExperimentIngredient.experiment_id == exp_row.id,
                    ExtExperimentIngredient.ingredient_id == ing_row.id,
                ).first()
                if not junction:
                    db.add(ExtExperimentIngredient(
                        experiment_id=exp_row.id,
                        ingredient_id=ing_row.id,
                        concentration=float(conc),
                        concentration_unit=ing_dict.get("concentration_unit") or "",
                    ))
                    db.flush()

            for meas_dict in exp_dict.get("measurements", []):
                day      = meas_dict.get("day")
                val      = meas_dict.get("indicator_value")
                ind_type = meas_dict.get("indicator_type") or ""
                ind_unit = meas_dict.get("indicator_unit") or ""
                if day is None or val is None or not ind_type:
                    continue
                ind_row = _get_ind(ind_type, ind_unit, meas_dict.get("indicator_threshold"))
                exists = db.query(ExtMeasurement).filter(
                    ExtMeasurement.experiment_id == exp_row.id,
                    ExtMeasurement.day == int(day),
                    ExtMeasurement.indicator_id == ind_row.id,
                ).first()
                if not exists:
                    db.add(ExtMeasurement(
                        experiment_id=exp_row.id,
                        day=int(day),
                        indicator_id=ind_row.id,
                        indicator_value=float(val),
                        value_is_approximate=bool(meas_dict.get("value_is_approximate", False)),
                    ))
                    db.flush()
                    meas_count += 1

        job.status = "completed"
        job.progress = 100
        job.current_step = f"Done — {exp_count} experiments, {meas_count} measurements"
        job.completed_at = datetime.utcnow()
        job.result_json = json.dumps({
            "experiments": exp_count,
            "measurements": meas_count,
            "reasoning": result.get("reasoning_summary", ""),
            "low_confidence_count": result.get("low_confidence_count", 0),
        })
        db.commit()

    except Exception as exc:
        logger.error("LLM validation failed for paper %d: %s", paper_id, exc, exc_info=True)
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = str(exc)[:500]
                job.completed_at = datetime.utcnow()
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.get("/projects/{project_id}/papers/{paper_id}/evidence-packages")
def get_evidence_packages(
    project_id: int,
    paper_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return grouped evidence items for the Validation page (no LLM call)."""
    _require_project(project_id, user, db)
    _get_paper(project_id, paper_id, db)

    assets = (
        db.query(ExtractionAsset)
        .filter(ExtractionAsset.paper_id == paper_id)
        .order_by(ExtractionAsset.relevance_score.desc(), ExtractionAsset.page_number)
        .all()
    )

    paragraphs: list = []
    native_tables: list = []
    chart_csvs: list = []
    excluded: list = []

    _NON_SCIENTIFIC = frozenset({"publisher_logo", "license_icon", "decorative_asset"})
    _AUTO_INCLUDE_SCORE = 3.0   # relevance threshold for automatic inclusion
    _AUTO_INCLUDE_TABLE_SCORE = 1.0  # lower bar for native tables (data-rich)

    for asset in assets:
        links = sorted(asset.context_links, key=lambda l: -(l.score or 0))
        link_data = [
            {
                "id": lnk.id,
                "link_type": lnk.link_type,
                "text": lnk.text[:500],
                "page_number": lnk.page_number,
                "score": lnk.score,
            }
            for lnk in links
        ]
        base = {**_asset_out(asset), "context_links": link_data, "link_count": len(links)}

        # ── Determine effective inclusion ─────────────────────────────────────
        # user_override: True = force include, False = force exclude, None = auto
        explicitly_selected = asset.selected_for_llm

        # Always exclude non-scientific assets (logos, decorative)
        is_decorative = asset.classification in _NON_SCIENTIFIC

        # Auto-include rule: high-relevance tables and charts that user hasn't
        # explicitly excluded (i.e., never manually touched → selected_for_llm
        # is still the default False from DB)
        auto_include = False
        auto_reason = None
        if not is_decorative:
            if asset.asset_type == "native_table" and asset.relevance_score >= _AUTO_INCLUDE_TABLE_SCORE:
                auto_include = True
                auto_reason = f"native table (relevance {asset.relevance_score:.1f})"
            elif asset.classification == "chart" and asset.csv_path and Path(asset.csv_path).exists():
                auto_include = True
                auto_reason = "chart CSV available"
            elif asset.relevance_score >= _AUTO_INCLUDE_SCORE:
                auto_include = True
                auto_reason = f"relevance score {asset.relevance_score:.1f}"

        # Effective decision:
        # - explicitly_selected overrides auto for figures/tables already touched by user
        # - decorative → always excluded
        effective_include = explicitly_selected or (auto_include and not is_decorative)

        base["auto_include"] = auto_include
        base["auto_reason"] = auto_reason
        base["is_decorative"] = is_decorative
        base["effective_include"] = effective_include

        if is_decorative:
            base["exclude_reason"] = f"decorative/non-scientific ({asset.classification})"
            excluded.append(base)
        elif not effective_include:
            base["exclude_reason"] = "low relevance score — not auto-selected"
            excluded.append(base)
        elif asset.asset_type == "native_table":
            native_tables.append(base)
        elif asset.classification == "chart" and asset.csv_path:
            chart_csvs.append(base)
        else:
            # Contribute text context links as paragraph evidence
            for lnk in links:
                if lnk.link_type in ("neighbor_before", "neighbor_after",
                                      "keyword_match", "same_section"):
                    paragraphs.append({
                        "asset_id": asset.id,
                        "link_id": lnk.id,
                        "link_type": lnk.link_type,
                        "text": lnk.text[:600],
                        "page_number": lnk.page_number or asset.page_number,
                        "score": lnk.score,
                        "section_name": asset.section_name,
                        "asset_caption": asset.caption,
                        "relevance_score": asset.relevance_score,
                        "auto_reason": auto_reason,
                    })

    # Check if any LLM job exists for this paper
    last_job = (
        db.query(Job)
        .filter(Job.paper_id == paper_id, Job.job_type == "llm_validation")
        .order_by(Job.id.desc())
        .first()
    )
    last_job_data = None
    if last_job:
        last_job_data = {
            "job_id": last_job.id,
            "status": last_job.status,
            "progress": last_job.progress or 0,
            "current_step": last_job.current_step or "",
            "result": json.loads(last_job.result_json) if last_job.result_json else None,
            "completed_at": last_job.completed_at.isoformat() if last_job.completed_at else None,
        }

    from app.services.chart_converter import _chart_model_error
    return {
        "paragraphs": paragraphs,
        "native_tables": native_tables,
        "chart_csvs": chart_csvs,
        "excluded": excluded,
        "totals": {
            "paragraphs": len(paragraphs),
            "native_tables": len(native_tables),
            "chart_csvs": len(chart_csvs),
            "excluded": len(excluded),
        },
        "chart_conversion_available": _chart_model_error is None,
        "chart_conversion_error": _chart_model_error,
        "last_job": last_job_data,
    }


@router.post("/projects/{project_id}/papers/{paper_id}/send-to-llm", status_code=202)
def send_to_llm(
    project_id: int,
    paper_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Trigger LLM extraction using pre-extracted workspace assets.
    Skips Docling — builds evidence packages from DB records directly.
    """
    _require_project(project_id, user, db)
    _get_paper(project_id, paper_id, db)

    total = db.query(ExtractionAsset).filter(ExtractionAsset.paper_id == paper_id).count()
    if total == 0:
        raise HTTPException(400, "No extracted assets found. Run the Docling pipeline first.")

    running = db.query(Job).filter(
        Job.paper_id == paper_id,
        Job.job_type == "llm_validation",
        Job.status.in_(["queued", "running"]),
    ).first()
    if running:
        return {"job_id": running.id, "status": "already_running"}

    selected = db.query(ExtractionAsset).filter(
        ExtractionAsset.paper_id == paper_id,
        ExtractionAsset.selected_for_llm == True,
    ).count()

    job = Job(
        project_id=project_id,
        paper_id=paper_id,
        job_type="llm_validation",
        status="queued",
        current_step="Queued",
        progress=0,
        created_by=user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_run_llm_validation, paper_id, project_id, job.id)

    return {
        "job_id": job.id,
        "status": "queued",
        "assets_selected": selected,
        "assets_total": total,
        "message": "LLM validation started",
    }


@router.get("/projects/{project_id}/papers/{paper_id}/llm-job/{job_id}")
def get_llm_job(
    project_id: int,
    paper_id: int,
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Poll LLM validation job status."""
    _require_project(project_id, user, db)
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.paper_id == paper_id,
        Job.project_id == project_id,
    ).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress or 0,
        "current_step": job.current_step or "",
        "error_message": job.error_message,
        "result": json.loads(job.result_json) if job.result_json else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
