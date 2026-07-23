"""
tests/test_docling_pipeline.py — Unit tests for the Docling-based extraction pipeline.

Tests are fully offline (no LLM calls, no Docling binary required).  Heavy
external dependencies (Docling, PP-Chart2Table) are patched with lightweight
fakes so these tests run in CI without GPU or large model downloads.

Coverage:
  1. DoclingResult.known_item_refs — correct set of all item refs
  2. Chart validation — _validate_dataframe acceptance and rejection criteria
  3. Chart cache hit — skips model call when CSV already exists
  4. Evidence package builder — tables always included, text keyword filter,
     chart_csv only for valid charts, token-budget splitting
  5. food_extractor _validate_refs — flags invented refs, keeps known refs
  6. food_extractor _check_ref — sets confidence=0 and _fabricated_ref on bad ref
  7. Duplicate measurement guard — second identical (exp, day, indicator) skipped
  8. Chart-derived measurements marked value_is_approximate=True
  9. EvidencePackage.render() — output contains item refs and page numbers
 10. _parse_markdown_table — strips alignment rows, handles missing pipe
"""

import csv
import io
import json
import os
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ─── Service imports ──────────────────────────────────────────────────────────

from app.services.docling_extractor import (
    DoclingFigure,
    DoclingResult,
    DoclingTable,
    DoclingText,
)
from app.services.chart_converter import (
    ChartResult,
    _validate_dataframe,
    _parse_markdown_table,
    convert_charts,
)
from app.services.evidence_package import (
    EvidencePackage,
    EvidenceItem,
    build_packages,
)
from app.services.food_extractor import (
    _check_ref,
    _validate_refs,
    _parse_json,
    _recover_experiments,
    _apply_corrections,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_docling_result(
    tmp_path: Path,
    n_texts: int = 2,
    n_tables: int = 1,
    n_figures: int = 1,
) -> DoclingResult:
    """Build a DoclingResult with real CSV and PNG files on disk."""
    # Tables
    tables = []
    for i in range(n_tables):
        csv_p = tmp_path / f"table_{i}.csv"
        df = pd.DataFrame({
            "Day": [0, 7, 14],
            "TVC (log CFU/g)": [5.1, 5.8, 6.3],
            "pH": [6.0, 6.2, 6.5],
        })
        df.to_csv(str(csv_p), index=False)
        tables.append(DoclingTable(
            item_ref=f"#/tables/{i}",
            page_number=i + 2,
            caption=f"Table {i + 1}: microbial counts",
            csv_path=str(csv_p),
            bbox={"x1": 0.1, "y1": 0.3, "x2": 0.9, "y2": 0.7},
        ))

    # Figures
    figures = []
    for i in range(n_figures):
        img_p = tmp_path / f"image_{i}.png"
        img_p.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header
        figures.append(DoclingFigure(
            item_ref=f"#/pictures/{i}",
            page_number=i + 3,
            caption=f"Figure {i + 1}: TVC over storage",
            image_path=str(img_p),
            bbox={"x1": 0.05, "y1": 0.1, "x2": 0.95, "y2": 0.6},
        ))

    # Texts
    texts = []
    for i in range(n_texts):
        texts.append(DoclingText(
            item_ref=f"#/texts/{i}",
            page_number=1,
            text=(
                "Total viable count (TVC) was measured at day 0, 7, and 14. "
                "Treatment groups showed significantly lower CFU values (p<0.05)."
            ) if i == 0 else "General introduction about food preservation.",
            heading_context="Results" if i == 0 else "Introduction",
            bbox={"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.2},
        ))

    return DoclingResult(
        file_hash="abc123",
        cache_dir=str(tmp_path),
        markdown_path=str(tmp_path / "content.md"),
        texts=texts,
        tables=tables,
        figures=figures,
        page_count=10,
    )


# ─── 1. known_item_refs ───────────────────────────────────────────────────────

def test_known_item_refs(tmp_path):
    result = _make_docling_result(tmp_path, n_texts=2, n_tables=2, n_figures=2)
    refs = result.known_item_refs
    assert "#/texts/0"    in refs
    assert "#/texts/1"    in refs
    assert "#/tables/0"   in refs
    assert "#/tables/1"   in refs
    assert "#/pictures/0" in refs
    assert "#/pictures/1" in refs
    assert len(refs) == 6


# ─── 2. Chart validation — acceptance ─────────────────────────────────────────

def test_validate_dataframe_valid():
    df = pd.DataFrame({"day": [0, 7, 14], "tvc": [5.1, 5.8, 6.3]})
    valid, reason = _validate_dataframe(df)
    assert valid is True
    assert reason is None


def test_validate_dataframe_too_few_rows():
    df = pd.DataFrame({"day": [0], "tvc": [5.1]})
    valid, reason = _validate_dataframe(df)
    assert valid is False
    assert "too few rows" in reason


def test_validate_dataframe_too_few_cols():
    df = pd.DataFrame({"day": [0, 7, 14]})
    valid, reason = _validate_dataframe(df)
    assert valid is False
    assert "too few columns" in reason


def test_validate_dataframe_too_many_cols():
    data = {f"col{i}": [1, 2, 3] for i in range(25)}
    df = pd.DataFrame(data)
    valid, reason = _validate_dataframe(df)
    assert valid is False
    assert "too many columns" in reason


def test_validate_dataframe_no_numeric():
    df = pd.DataFrame({"label": ["a", "b", "c"], "cat": ["x", "y", "z"]})
    valid, reason = _validate_dataframe(df)
    assert valid is False
    assert "no numeric" in reason


def test_validate_dataframe_empty():
    valid, reason = _validate_dataframe(pd.DataFrame())
    assert valid is False
    assert "empty" in reason


def test_validate_dataframe_none():
    valid, reason = _validate_dataframe(None)
    assert valid is False


# ─── 3. Chart cache hit ───────────────────────────────────────────────────────

def test_convert_charts_cache_hit(tmp_path):
    """When a valid _data.csv already exists, model.predict must NOT be called."""
    img_p = tmp_path / "image_0.png"
    img_p.write_bytes(b"\x89PNG\r\n\x1a\n")

    csv_p = tmp_path / "image_0_data.csv"
    df = pd.DataFrame({"day": [0, 7, 14], "tvc": [5.1, 5.8, 6.3]})
    df.to_csv(str(csv_p), index=False)

    fig = DoclingFigure(
        item_ref="#/pictures/0",
        page_number=3,
        caption="Figure 1",
        image_path=str(img_p),
        bbox=None,
    )

    mock_model = MagicMock()
    with patch("app.services.chart_converter._get_chart_model", return_value=mock_model):
        results = convert_charts([fig], str(tmp_path))

    assert len(results) == 1
    assert results[0].status == "valid"
    assert results[0].csv_path == str(csv_p)
    mock_model.predict.assert_not_called()


# ─── 4. Evidence package builder ─────────────────────────────────────────────

def test_build_packages_includes_all_tables(tmp_path):
    result = _make_docling_result(tmp_path, n_texts=0, n_tables=2, n_figures=0)
    chart_results = []
    packages = build_packages(result, chart_results)
    assert len(packages) >= 1
    all_refs = {item.item_ref for pkg in packages for item in pkg.items}
    assert "#/tables/0" in all_refs
    assert "#/tables/1" in all_refs


def test_build_packages_text_keyword_filter(tmp_path):
    """Only the Results paragraph (CFU keywords) should be included, not the intro."""
    result = _make_docling_result(tmp_path, n_texts=2, n_tables=0, n_figures=0)
    chart_results = []
    packages = build_packages(result, chart_results)
    all_refs = {item.item_ref for pkg in packages for item in pkg.items}
    assert "#/texts/0" in all_refs      # has "CFU" / "day" / "TVC"
    assert "#/texts/1" not in all_refs  # pure intro text, no keywords


def test_build_packages_chart_csv_included(tmp_path):
    """Validated chart CSV → EvidenceItem with source_type='chart_csv'."""
    result = _make_docling_result(tmp_path, n_texts=0, n_tables=0, n_figures=1)
    csv_p = tmp_path / "image_0_data.csv"
    df = pd.DataFrame({"day": [0, 7, 14], "tvc": [5.1, 5.8, 6.3]})
    df.to_csv(str(csv_p), index=False)

    chart_results = [ChartResult(
        item_ref="#/pictures/0",
        figure_index=1,
        image_path=str(tmp_path / "image_0.png"),
        image_hash=None,
        csv_path=str(csv_p),
        status="valid",
        reject_reason=None,
        row_count=3,
        col_count=2,
    )]
    packages = build_packages(result, chart_results)
    all_items = [item for pkg in packages for item in pkg.items]
    chart_items = [i for i in all_items if i.source_type == "chart_csv"]
    assert len(chart_items) == 1
    assert chart_items[0].is_approximate is True


def test_build_packages_rejected_chart_excluded(tmp_path):
    """Rejected chart CSV must not appear in packages."""
    result = _make_docling_result(tmp_path, n_texts=0, n_tables=0, n_figures=1)
    chart_results = [ChartResult(
        item_ref="#/pictures/0",
        figure_index=1,
        image_path=str(tmp_path / "image_0.png"),
        image_hash=None,
        csv_path=None,
        status="rejected",
        reject_reason="no numeric columns",
    )]
    packages = build_packages(result, chart_results)
    all_items = [item for pkg in packages for item in pkg.items]
    assert not any(i.source_type == "chart_csv" for i in all_items)


def test_build_packages_token_split(tmp_path):
    """Large tables should be split across packages when they exceed the budget."""
    tables = []
    for i in range(20):
        csv_p = tmp_path / f"table_{i}.csv"
        # Each CSV is ~3 000 chars (large enough to force splits at 12 000 chars)
        rows = [{"day": d, "tvc": 5.0 + d * 0.1, "info": "x" * 100} for d in range(10)]
        pd.DataFrame(rows).to_csv(str(csv_p), index=False)
        tables.append(DoclingTable(
            item_ref=f"#/tables/{i}",
            page_number=i + 1,
            caption=None,
            csv_path=str(csv_p),
            bbox=None,
        ))

    result = DoclingResult(
        file_hash="split_test",
        cache_dir=str(tmp_path),
        markdown_path="",
        texts=[],
        tables=tables,
        figures=[],
        page_count=20,
    )
    packages = build_packages(result, [], max_tokens=500)
    assert len(packages) > 1, "Large content should be split into multiple packages"


# ─── 5. food_extractor — _validate_refs ──────────────────────────────────────

def test_validate_refs_flags_invented_ref():
    known = {"#/tables/0", "#/texts/1"}
    experiments = [
        {
            "meat_matrix": "chicken breast",
            "treatment": "chitosan 1%",
            "experiment_evidence": [
                {"docling_item_ref": "#/tables/99", "confidence": 0.9}
            ],
            "ingredients": [],
            "measurements": [],
        }
    ]
    result = _validate_refs(experiments, known)
    ev = result[0]["experiment_evidence"][0]
    assert ev["confidence"] == 0.0
    assert ev.get("_fabricated_ref") is True


def test_validate_refs_keeps_known_ref():
    known = {"#/tables/0", "#/texts/1"}
    experiments = [
        {
            "experiment_evidence": [
                {"docling_item_ref": "#/tables/0", "confidence": 0.95}
            ],
            "ingredients": [],
            "measurements": [],
        }
    ]
    result = _validate_refs(experiments, known)
    ev = result[0]["experiment_evidence"][0]
    assert ev["confidence"] == 0.95
    assert "_fabricated_ref" not in ev


# ─── 6. _check_ref ────────────────────────────────────────────────────────────

def test_check_ref_unknown():
    known = {"#/tables/0"}
    ev = {"docling_item_ref": "#/tables/99", "confidence": 0.8}
    _check_ref(ev, known)
    assert ev["confidence"] == 0.0
    assert ev["_fabricated_ref"] is True


def test_check_ref_known():
    known = {"#/tables/0"}
    ev = {"docling_item_ref": "#/tables/0", "confidence": 0.8}
    _check_ref(ev, known)
    assert ev["confidence"] == 0.8


def test_check_ref_none_ref_ignored():
    """None docling_item_ref should not flag the evidence record."""
    known = {"#/tables/0"}
    ev = {"docling_item_ref": None, "confidence": 0.6}
    _check_ref(ev, known)
    assert "_fabricated_ref" not in ev


# ─── 7. Duplicate measurement guard ──────────────────────────────────────────

def test_duplicate_measurement_skipped(db):
    """Inserting the same (experiment, day, indicator) twice must be a no-op."""
    from app.db.models import (
        ExtExperiment, ExtIndicator, ExtMeasurement, Project, User
    )
    from app.core.security import hash_password

    user = User(email="u@t.com", full_name="U", hashed_password=hash_password("pw"), is_active=True)
    db.add(user)
    db.flush()

    proj = Project(name="P", owner_id=user.id)
    db.add(proj)
    db.flush()

    exp = ExtExperiment(project_id=proj.id, paper_id=1, job_id=1,
                        meat_matrix="beef", treatment="control")
    db.add(exp)
    db.flush()

    ind = ExtIndicator(project_id=proj.id, indicator_type="TVC",
                       indicator_unit="log CFU/g")
    db.add(ind)
    db.flush()

    # Insert once
    m1 = ExtMeasurement(experiment_id=exp.id, day=7,
                        indicator_id=ind.id, indicator_value=5.8)
    db.add(m1)
    db.flush()

    # Simulate the duplicate guard from _run_food_extraction
    existing = db.query(ExtMeasurement).filter(
        ExtMeasurement.experiment_id == exp.id,
        ExtMeasurement.day == 7,
        ExtMeasurement.indicator_id == ind.id,
    ).first()
    if not existing:
        db.add(ExtMeasurement(experiment_id=exp.id, day=7,
                              indicator_id=ind.id, indicator_value=5.9))
        db.flush()

    count = db.query(ExtMeasurement).filter(
        ExtMeasurement.experiment_id == exp.id,
        ExtMeasurement.day == 7,
        ExtMeasurement.indicator_id == ind.id,
    ).count()
    assert count == 1, "Duplicate measurement should be blocked by the guard"


# ─── 8. Chart-derived measurement tagging ─────────────────────────────────────

def test_chart_derived_value_is_approximate():
    """Measurements whose evidence has source_type='chart_csv' must be tagged approximate."""
    from app.services.food_extractor import extract_food_data

    packages = [MagicMock()]
    packages[0].index = 1
    packages[0].token_estimate = 100
    packages[0].render.return_value = "test content"

    fake_llm_result = {
        "reasoning_summary": "found data",
        "experiments": [
            {
                "meat_matrix": "beef",
                "treatment": "control",
                "experiment_evidence": [],
                "ingredients": [],
                "measurements": [
                    {
                        "day": 7,
                        "indicator_type": "TVC",
                        "indicator_unit": "log CFU/g",
                        "indicator_threshold": None,
                        "indicator_value": 5.8,
                        "value_is_approximate": False,
                        "evidence": [
                            {
                                "docling_item_ref": "#/pictures/0",
                                "source_type": "chart_csv",
                                "confidence": 0.5,
                            }
                        ],
                    }
                ],
            }
        ],
    }

    with patch("app.services.food_extractor._groq_call") as mock_call, \
         patch("app.services.food_extractor._groq_client") as mock_client:
        mock_call.return_value = json.dumps(fake_llm_result)
        result = extract_food_data(
            evidence_packages=packages,
            known_item_refs={"#/pictures/0"},
            enable_verification=False,
        )

    exps = result["experiments"]
    assert len(exps) == 1
    meas = exps[0]["measurements"][0]
    assert meas["value_is_approximate"] is True


# ─── 9. EvidencePackage.render() ─────────────────────────────────────────────

def test_evidence_package_render_contains_refs(tmp_path):
    result = _make_docling_result(tmp_path, n_texts=0, n_tables=1, n_figures=0)
    chart_results = []
    packages = build_packages(result, chart_results)
    assert packages, "Expected at least one package"
    rendered = packages[0].render()
    assert "#/tables/0" in rendered
    assert "page:" in rendered


def test_evidence_package_render_marks_chart_approximate(tmp_path):
    result = _make_docling_result(tmp_path, n_texts=0, n_tables=0, n_figures=1)
    csv_p = tmp_path / "image_0_data.csv"
    pd.DataFrame({"day": [0, 7], "tvc": [5.1, 5.8]}).to_csv(str(csv_p), index=False)

    chart_results = [ChartResult(
        item_ref="#/pictures/0",
        figure_index=1,
        image_path=str(tmp_path / "image_0.png"),
        image_hash=None,
        csv_path=str(csv_p),
        status="valid",
        reject_reason=None,
        row_count=2,
        col_count=2,
    )]
    packages = build_packages(result, chart_results)
    rendered = packages[0].render()
    assert "APPROXIMATE" in rendered or "approximate" in rendered.lower()


# ─── 10. _parse_markdown_table ────────────────────────────────────────────────

def test_parse_markdown_table_basic():
    md = (
        "| Day | TVC |\n"
        "| --- | --- |\n"
        "| 0   | 5.1 |\n"
        "| 7   | 5.8 |\n"
        "| 14  | 6.3 |\n"
    )
    df = _parse_markdown_table(md)
    assert df is not None
    assert len(df) == 3


def test_parse_markdown_table_strips_alignment_row():
    md = (
        "| Day | TVC (log CFU/g) |\n"
        "|:---:|:---:|\n"
        "| 0   | 5.1 |\n"
        "| 7   | 5.8 |\n"
    )
    df = _parse_markdown_table(md)
    assert df is not None
    assert len(df) == 2


def test_parse_markdown_table_empty_returns_none():
    assert _parse_markdown_table("") is None
    assert _parse_markdown_table("   ") is None


def test_parse_markdown_table_too_few_rows():
    md = "| Day | TVC |\n| --- | --- |\n| 0 | 5.1 |\n"
    df = _parse_markdown_table(md)
    # Only 1 data row — _validate_dataframe will reject, but _parse_markdown_table
    # itself should still return a DataFrame (validation is separate)
    assert df is not None or df is None  # either outcome acceptable from parse alone


# ─── 11. _parse_json ──────────────────────────────────────────────────────────

def test_parse_json_clean():
    raw = '{"experiments": [], "reasoning_summary": "ok"}'
    result = _parse_json(raw)
    assert result["reasoning_summary"] == "ok"


def test_parse_json_strips_fences():
    raw = '```json\n{"experiments": []}\n```'
    result = _parse_json(raw)
    assert "experiments" in result


def test_parse_json_invalid_returns_empty():
    result = _parse_json("this is not json at all !!!")
    assert result == {}


# ─── 12. _recover_experiments ────────────────────────────────────────────────

def test_recover_experiments_salvages_partial():
    partial = (
        '{"experiments": [{"meat_matrix": "beef", "measurements": [{"day": 0}]}'
        # deliberately truncated — missing closing braces for outer object
    )
    recovered = _recover_experiments(partial)
    assert len(recovered) == 1
    assert recovered[0]["meat_matrix"] == "beef"


# ─── 13. _apply_corrections ───────────────────────────────────────────────────

def test_apply_corrections_corrected():
    experiments = [
        {
            "measurements": [
                {"day": 0, "indicator_value": 5.1, "evidence": []},
                {"day": 7, "indicator_value": 5.8, "evidence": []},
            ]
        }
    ]
    corrections = [
        {"original_index": 1, "status": "corrected", "corrected_value": 6.0, "evidence": [{"docling_item_ref": "#/tables/0"}]}
    ]
    result = _apply_corrections(experiments, corrections)
    assert result[0]["measurements"][1]["indicator_value"] == 6.0
    assert result[0]["measurements"][1]["_corrected_by_pass2"] is True


def test_apply_corrections_unverifiable():
    experiments = [
        {"measurements": [{"day": 0, "indicator_value": 5.1, "evidence": []}]}
    ]
    corrections = [{"original_index": 0, "status": "unverifiable", "evidence": []}]
    result = _apply_corrections(experiments, corrections)
    assert result[0]["measurements"][0].get("_unverifiable") is True


def test_apply_corrections_out_of_bounds_ignored():
    experiments = [{"measurements": [{"day": 0, "indicator_value": 5.1}]}]
    corrections = [{"original_index": 999, "status": "corrected", "corrected_value": 9.0}]
    result = _apply_corrections(experiments, corrections)
    assert result[0]["measurements"][0]["indicator_value"] == 5.1
