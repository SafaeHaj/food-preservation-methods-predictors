"""
Pipeline orchestrator: ties Stages 1–5 together for a given food matrix.

Entry point: run_pipeline(matrix, config_dir, data_dir, model_id, ...)
"""

from __future__ import annotations

from pathlib import Path

from src.data_retrieval.extractor import run_extraction
from src.data_retrieval.filter import run_filter
from src.data_retrieval.parser import run_parsing
from src.data_retrieval.schema_loader import (
    build_extraction_model,
    get_anchor_concepts,
    load_schema,
)
from src.data_retrieval.searcher import run_search
from src.data_retrieval.storage import run_storage


def run_pipeline(
    matrix: str,
    config_dir: Path,
    data_dir: Path,
    model_id: str = "gpt-4o-mini",
    api_key: str | None = None,
    skip_download: bool = False,
    skip_parsing: bool = False,
) -> None:
    """
    Execute the full literature extraction pipeline for a food matrix.

    Args:
        matrix:        Food matrix identifier (e.g. "meat"). Must match a key in
                       search.json and a file configs/schemas/{matrix}_schema.yaml.
        config_dir:    Path to the configs/ directory.
        data_dir:      Path to the data/ directory (subdirs created automatically).
        model_id:      LiteLLM model string (e.g. "gpt-4o-mini", "claude-haiku-4-5-20251001").
        api_key:       Semantic Scholar API key (optional; unauthenticated works at lower rate).
        skip_download: Skip Stage 1; use existing PDFs in raw_pdfs/{matrix}/.
        skip_parsing:  Skip Stage 2; use existing Markdown in parsed_markdown/{matrix}/.
    """
    # --- Paths ---
    schema_path = config_dir / "schemas" / f"{matrix}_schema.yaml"
    search_config_path = config_dir / "search.json"
    pdf_dir = data_dir / "raw_pdfs" / matrix
    md_dir = data_dir / "parsed_markdown" / matrix
    out_dir = data_dir / "extracted_json" / matrix
    log_dir = data_dir / "pipeline_logs"

    for d in (pdf_dir, md_dir, out_dir, log_dir):
        d.mkdir(parents=True, exist_ok=True)

    # --- Load schema & build Pydantic model ---
    print(f"\n=== Pipeline: matrix='{matrix}' model='{model_id}' ===\n")
    schema = load_schema(schema_path)
    extraction_model = build_extraction_model(schema)
    anchor_concepts = get_anchor_concepts(schema)

    # --- Stage 1: Search & Download ---
    if not skip_download:
        run_search(matrix, search_config_path, pdf_dir, api_key)
    else:
        n = len(list(pdf_dir.glob("*.pdf")))
        print(f"[pipeline] Skipping download — {n} existing PDFs in {pdf_dir}")

    # --- Stage 2: PDF → Markdown ---
    if not skip_parsing:
        run_parsing(pdf_dir, md_dir)
    else:
        n = len(list(md_dir.glob("*.md")))
        print(f"[pipeline] Skipping parsing — {n} existing Markdown files in {md_dir}")

    # --- Stage 3: Anchor-based filter ---
    rejection_log = log_dir / f"{matrix}_filter_rejections.jsonl"
    passed_md = run_filter(md_dir, anchor_concepts, rejection_log)

    if not passed_md:
        print("[pipeline] No papers passed the relevance filter. Stopping.")
        return

    # --- Stage 4: LLM Extraction ---
    results = run_extraction(passed_md, schema, extraction_model, model_id)

    # --- Stage 5: Save JSON ---
    run_storage(results, out_dir, schema)

    print(f"\n=== Pipeline complete. Results in {out_dir} ===\n")
