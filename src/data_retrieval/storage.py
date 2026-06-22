"""
Stage 5: Persist validated extraction results as JSON files.

Output uses db_keys (not aliases). Each file also carries provenance metadata.

Entry point: run_storage(extraction_results, output_dir, schema) -> list[Path]
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from src.data_retrieval.schema_loader import to_db_dict


def next_paper_id(output_dir: Path) -> str:
    """Return the next sequential paper ID string, e.g. 'paper_003'."""
    existing = sorted(output_dir.glob("paper_*.json"))
    if not existing:
        return "paper_001"
    last = existing[-1].stem  # e.g. "paper_007"
    try:
        n = int(last.split("_")[-1])
    except ValueError:
        n = len(existing)
    return f"paper_{n + 1:03d}"


def save_extraction(
    record: BaseModel,
    source_md_path: Path,
    output_dir: Path,
) -> Path:
    """
    Serialize record to paper_NNN.json using db_keys.

    Adds _source_file and _extracted_at provenance fields.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paper_id = next_paper_id(output_dir)
    out_path = output_dir / f"{paper_id}.json"

    payload = to_db_dict(record)
    payload["_source_file"] = source_md_path.name
    payload["_extracted_at"] = datetime.now(timezone.utc).isoformat()

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return out_path


def run_storage(
    extraction_results: list[tuple[Path, BaseModel | Exception]],
    output_dir: Path,
    schema: dict,  # kept for signature consistency; to_db_dict uses model internals
) -> list[Path]:
    """
    Save all successful extraction results.

    Skips failures with a log message. Returns list of written file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    for md_path, result in extraction_results:
        if isinstance(result, Exception):
            print(f"  [storage] Skipping {md_path.name} (extraction failed)")
            continue
        out_path = save_extraction(result, md_path, output_dir)
        print(f"  [storage] Saved: {out_path.name} <- {md_path.name}")
        saved.append(out_path)

    print(f"[storage] {len(saved)} records written to {output_dir}")
    return saved
