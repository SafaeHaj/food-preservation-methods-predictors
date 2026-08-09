"""Silver: clean everything, gate everything, and say why for each.

The output is one package per paper — the assets that passed with their observations
parsed into (axis, label, value) tuples, the reference tables, the ones the gate could not
key, and the rejects with a stage and a reason. Gold reads only this; it never sees a PDF.

Four verdicts, and the distinction between the last three is the point:

  accepted   an ordered axis with values along it — a series the pipeline can read
  reference  a catalogue of entities against quantities (an oil's composition), which is
             where ingredients come from but never measurements
  review     shaped like data, but no axis found — usually a table the gate misread, so
             the model is asked to name the axis column and the gate re-reads it
  rejected   with the stage that rejected it, so a corpus-wide miss is visible
"""

from __future__ import annotations

import json
import logging
from itertools import chain
from pathlib import Path
from typing import Any, Optional, Sequence

import polars as pl

from shared.config import get_common_settings, get_extraction_settings
from shared.schemas.silver import PACKAGE_VERSION, SilverPackage
from shared.science.gate import (
    MIN_AXIS_POINTS, MIN_NUMERIC_RATIO, SchemaFit, canonical_key, column_label, fits_schema,
    observation_payload,
)

from app.services.silver import charts as chart_stage
from app.services.silver.probe import plot_likeness
from app.services.silver.sections import (
    build_text_index, local_context, methods_section_refs, paper_sections,
)
from app.services.silver.tables import (
    as_markdown_table, clean_table_frame, frame_to_records, read_table_csv, write_records_csv,
)

logger = logging.getLogger(__name__)
_settings = get_extraction_settings()
_common = get_common_settings()

#: Bumped when the gate's behaviour changes, so cached packages are not reused across it.
GATE_VERSION = "gate-3"

#: Distinct named rows a table needs before it reads as a catalogue rather than a stub.
MIN_REFERENCE_ENTITIES = 3

GATED_SECTIONS = ("tables", "figures", "references", "review", "rejected")
_VERDICT_SECTION = {"reference": "references", "review": "review", "rejected": "rejected"}

#: One malformed asset costs itself, not the paper. Anything outside this list is a bug in
#: the gate rather than a bad table, and is allowed to fail the run.
ASSET_FAILURES = (ValueError, TypeError, KeyError, IndexError, OSError, pl.exceptions.PolarsError)


# ─── Asset metadata ───────────────────────────────────────────────────────────

def _table_meta(table, index: int) -> dict:
    return {
        "docling_item_ref": table.item_ref,
        "table_index": index,
        "caption": table.caption,
        "page_number": table.page_number,
        "order": table.order,
        "csv_path": table.csv_path,
        "bbox": table.bbox,
    }


def _figure_meta(figure, index: int) -> dict:
    return {
        "docling_item_ref": figure.item_ref,
        "figure_index": index,
        "caption": figure.caption,
        "page_number": figure.page_number,
        "order": figure.order,
        "image_path": figure.image_path,
        "bbox": figure.bbox,
    }


def _asset_base(meta: dict, kind: str) -> dict:
    return {
        "kind": kind,
        "index": meta.get("table_index") if kind == "table" else meta.get("figure_index"),
        "docling_item_ref": meta.get("docling_item_ref"),
        "caption": meta.get("caption"),
        "page_number": meta.get("page_number"),
    }


# ─── Records ──────────────────────────────────────────────────────────────────

def _gated_record(meta: dict, fit: SchemaFit, text_index: dict, headers, **extra) -> dict:
    return {**meta, "headers": headers, "gate": fit.summary(),
            **local_context(text_index, meta), **extra}


def _review_record(meta: dict, fit: SchemaFit, text_index: dict, headers, rows, **extra) -> dict:
    """Kept whole: `adjudicate_review` re-gates these rows once the model names the axis."""
    return _gated_record(
        meta, fit, text_index, headers, rows=rows, why=fit.reason,
        preview_markdown=as_markdown_table(headers, rows, limit=_settings.REVIEW_PREVIEW_ROWS),
        **extra)


def _accepted_record(meta: dict, fit: SchemaFit, text_index: dict, headers, rows, **extra) -> dict:
    return _gated_record(
        meta, fit, text_index, headers,
        preview_markdown=as_markdown_table(headers, rows),
        observations=observation_payload(fit), **extra)


# ─── Verdicts ─────────────────────────────────────────────────────────────────

def _is_reference_table(fit: SchemaFit, row_count: int) -> bool:
    """A catalogue of entities against quantities — a column of distinct names beside a
    column of numbers — rather than a series over time.

    A column whose labels key an axis is a series that was not read, not a catalogue, so it
    disqualifies the whole table.
    """
    if not fit.columns or row_count < MIN_REFERENCE_ENTITIES:
        return False
    names = numbers = False
    for column in fit.columns:
        if not column.entries:
            continue
        if column.numeric_ratio >= MIN_NUMERIC_RATIO:
            numbers = True
        elif column.keys_an_axis:
            return False
        elif len(set(column.entries)) >= MIN_REFERENCE_ENTITIES:
            names = True
    return names and numbers


def _could_key_an_axis(column) -> bool:
    """Three distinct positions in the column's own labels — what the keyed fit needs
    before it will accept the column, whether it chose it or the model named it."""
    return len({position for position, _ in column.keyed if position is not None}) \
        >= MIN_AXIS_POINTS


def _needs_review(fit: SchemaFit) -> bool:
    """Shaped like data, but the gate could not key it.

    Numbers and labels, no axis in either: far more often a measurement table the gate
    misread than it is furniture, so it goes to the model to have its axis named rather
    than into `rejected`.

    Only where an answer could change the verdict. The model is asked for the name of a
    column, and the keyed fit that unlocks needs three distinct positions in that column's
    own cells — a table where no label column carries three is one no answer can promote,
    and asking about it spends a whole reasoning call to be told nothing.
    """
    if not fit.columns:
        return False
    if not any(column.is_numeric for column in fit.columns):
        return False
    return any(_could_key_an_axis(column) for column in fit.columns
               if not column.is_numeric and column.entries)


# ─── Per-asset gating ─────────────────────────────────────────────────────────

def gate_table(meta: dict, text_index: dict, tables_dir: Path) -> tuple:
    """Clean, gate and stage one native table. Returns (verdict, record)."""
    base = _asset_base(meta, "table")
    csv_path = meta.get("csv_path")
    if not csv_path or not Path(csv_path).exists():
        return "rejected", {**base, "stage": "bronze", "reason": "no CSV"}

    frame = clean_table_frame(read_table_csv(csv_path))
    headers, rows = frame_to_records(frame)
    fit = fits_schema(headers, rows)
    cleaned_csv_path = tables_dir / Path(csv_path).name
    staged = {"cleaned_csv_path": str(cleaned_csv_path)}

    if not fit.fits:
        if _is_reference_table(fit, len(rows)):
            frame.write_csv(cleaned_csv_path)
            return "reference", _gated_record(
                meta, fit, text_index, headers, rows=rows, **staged,
                why=f"no measurement axis ({fit.reason}); rows name entities")
        if _needs_review(fit):
            frame.write_csv(cleaned_csv_path)
            return "review", _review_record(meta, fit, text_index, headers, rows,
                                            is_figure=False, **staged)
        return "rejected", {**base, "stage": "schema_gate", "reason": fit.reason}

    frame.write_csv(cleaned_csv_path)
    return "accepted", _accepted_record(
        meta, fit, text_index, headers, rows, is_figure=False, **staged,
        row_count=frame.height, col_count=frame.width)


def probe_figure(meta: dict, text_index: Optional[dict] = None) -> tuple:
    """Cheap visual test, no model.

    Split from the gate so every survivor converts in one batched call, and given the words
    around the figure so the caption filter has something to read.
    """
    base = _asset_base(meta, "figure")
    if not meta.get("image_path"):
        return "rejected", {**base, "stage": "bronze", "reason": "no image"}
    nearby = (local_context(text_index, meta)["context_markdown"]
              if text_index is not None else None)
    probe = plot_likeness(meta["image_path"], caption=meta.get("caption"), nearby_text=nearby)
    if not probe.plot_like:
        return "rejected", {**base, "stage": "probe", "reason": probe.reason,
                            "probe": probe.summary()}
    return "probed", probe


def gate_converted_figure(meta: dict, probe, conversion: dict,
                          text_index: dict, figures_dir: Path) -> tuple:
    """Gate one already-converted figure. Returns (verdict, record)."""
    base = _asset_base(meta, "figure")
    if conversion["status"] != "converted":
        if conversion["status"] == "unavailable" and not _settings.REQUIRE_FIGURE_DATA:
            return "accepted", {
                **meta,
                "is_figure": True,
                "probe": probe.summary(),
                "conversion_status": "unavailable",
                "gate": {"fits": None, "reason": "admitted on the visual probe alone"},
                "observations": [],
                **local_context(text_index, meta),
            }
        return "rejected", {
            **base,
            "stage": "conversion",
            "reason": conversion.get("error") or conversion["status"],
            "probe": probe.summary(),
        }

    headers, rows = conversion["headers"], conversion["rows"]
    fit = fits_schema(headers, rows)
    figure_csv_path = figures_dir / f"figure_{meta['figure_index']:03d}.csv"
    staged = {"is_figure": True, "probe": probe.summary(), "conversion_status": "converted",
              "csv_path": str(figure_csv_path)}

    if not fit.fits:
        if not _needs_review(fit):
            return "rejected", {**base, "stage": "schema_gate", "reason": fit.reason,
                                "probe": probe.summary()}
        write_records_csv(headers, rows, figure_csv_path)
        return "review", _review_record(meta, fit, text_index, headers, rows, **staged)

    write_records_csv(headers, rows, figure_csv_path)
    return "accepted", _accepted_record(meta, fit, text_index, headers, rows, **staged)


# ─── Assembly ─────────────────────────────────────────────────────────────────

def _dispatch(gated: dict, accepted: str, verdict: str, record: dict) -> None:
    gated[accepted if verdict == "accepted" else _VERDICT_SECTION[verdict]].append(record)


def _reject(gated: dict, meta: dict, kind: str, exc: BaseException) -> None:
    gated["rejected"].append({**_asset_base(meta, kind), "stage": "error",
                              "reason": f"{type(exc).__name__}: {exc}"})


def _caption_verdicts(gated: dict) -> dict:
    """How every figure's own caption read, whether or not it reached the model.

    With FIGURE_REQUIRE_PLOT_CAPTION on this is the cost story -- "plot" is what was paid
    for -- and with it off it is the estimate of what turning it on would save, without
    re-running the corpus to find out.
    """
    counts: dict[str, int] = {}
    for record in chain(*gated.values()):
        probe = record.get("probe")
        if not isinstance(probe, dict):
            continue
        verdict = probe.get("own_caption_verdict", "unknown")
        counts[verdict] = counts.get(verdict, 0) + 1
    return dict(sorted(counts.items()))


def _gate_report(tables_in: int, figures_in: int, figures_converted: int,
                 gated: dict) -> dict:
    rejected = gated["rejected"]
    return {
        "tables_in": tables_in,
        "tables_accepted": len(gated["tables"]),
        "figures_in": figures_in,
        #: Figures actually sent to the chart model, i.e. everything the probe let past.
        #: The gap to `figures_in` is the work the filters saved.
        "figures_converted": figures_converted,
        "figures_accepted": len(gated["figures"]),
        "caption_verdicts": _caption_verdicts(gated),
        "rejected_by_stage": {
            stage: sum(1 for item in rejected if item["stage"] == stage)
            for stage in sorted({item["stage"] for item in rejected})
        },
        "references": len(gated["references"]),
        "review": len(gated["review"]),
        "observations": sum(len(item.get("observations") or [])
                            for item in chain(gated["tables"], gated["figures"])),
    }


def build_package(result, *, paper_slug: str) -> dict:
    """Everything Silver decides for one paper: gate every table, convert and gate every
    figure that survives the visual probe.

    Takes a `DoclingResult` — the Bronze contract — so it can run against a live parse, a
    cached one or a fixture without three code paths.
    """
    cache_dir = Path(result.cache_dir)
    tables_dir = cache_dir / "silver" / "tables"
    figures_dir = cache_dir / "silver" / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    text_index = build_text_index(result)
    sections, section_source = paper_sections(result)
    gated: dict = {name: [] for name in GATED_SECTIONS}

    for index, table in enumerate(result.tables):
        meta = _table_meta(table, index)
        try:
            _dispatch(gated, "tables", *gate_table(meta, text_index, tables_dir))
        except ASSET_FAILURES as exc:
            logger.warning("Table %s failed in the gate: %s", table.item_ref, exc)
            _reject(gated, meta, "table", exc)

    probed = []
    for index, figure in enumerate(result.figures):
        meta = _figure_meta(figure, index)
        try:
            verdict, payload = probe_figure(meta, text_index)
        except ASSET_FAILURES as exc:
            logger.warning("Figure %s failed in the probe: %s", figure.item_ref, exc)
            _reject(gated, meta, "figure", exc)
            continue
        if verdict == "probed":
            probed.append((meta, payload))
        else:
            gated["rejected"].append(payload)

    conversions = chart_stage.convert_figures([meta["image_path"] for meta, _ in probed])
    for (meta, probe), conversion in zip(probed, conversions):
        try:
            _dispatch(gated, "figures",
                      *gate_converted_figure(meta, probe, conversion, text_index, figures_dir))
        except ASSET_FAILURES as exc:
            logger.warning("Figure %s failed in the gate: %s", meta["docling_item_ref"], exc)
            _reject(gated, meta, "figure", exc)

    return {
        "paper_slug": paper_slug,
        "file_hash": result.file_hash,
        "cache_dir": str(cache_dir),
        "markdown_path": result.markdown_path,
        "page_count": result.page_count,
        "sections": sections,
        "section_source": section_source,
        "methods_refs": sorted(methods_section_refs(sections)),
        "texts": text_index["all"],
        "gate_report": _gate_report(len(result.tables), len(result.figures),
                                    len(probed), gated),
        "cache_key": cache_key(result),
        **gated,
    }


# ─── Persistence between the two jobs ─────────────────────────────────────────

def cache_key(result) -> str:
    """Content-addressed: the parse and the gate's version, and nothing else.

    The vocabulary used to be in the key, back when normalisation ran here. It is not any
    more -- the key names what *extraction* produced, and extraction's output does not
    depend on any term. A vocabulary edit now invalidates the ingestion result, which is a
    job re-run of seconds, instead of forcing every paper back through Docling and
    PP-Chart2Table.
    """
    return f"{result.file_hash}.{GATE_VERSION}"


def package_path(key: str) -> Path:
    directory = _common.silver_cache_path
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{key}.json"


def save(package: dict) -> Path:
    """Validate, then write.

    Validating here rather than on read is deliberate: a package processing could not parse
    fails in *this* job, where the paper and the stage are on screen, instead of surfacing
    hours later as a `KeyError` three modules deep in someone else's service.
    """
    package["package_version"] = PACKAGE_VERSION
    SilverPackage.model_validate(package)
    path = package_path(package["cache_key"])
    path.write_text(json.dumps(package, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def load(path: Optional[str], expected_key: Optional[str] = None) -> Optional[dict]:
    """Read a stored package. None when it is missing, unreadable, or from another gate.

    A stale pointer is not an error: the caller recomputes Silver from the cached parse,
    which is cheap next to re-reading the PDF.
    """
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        package = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Silver package at %s is unreadable; recomputing", candidate)
        return None
    if expected_key and package.get("cache_key") != expected_key:
        return None
    return package


# ─── Reporting ────────────────────────────────────────────────────────────────

def decisions(package: dict) -> list[dict]:
    """Every asset and what the gate did with it — the `/gate-report` body.

    The single most useful view when a paper produces less than expected: it names which
    table was rejected and at which stage, rather than leaving an empty result to explain
    itself.
    """
    rows = []
    for section, verdict in (("tables", "accepted"), ("figures", "accepted"),
                             ("references", "reference"), ("review", "review"),
                             ("rejected", "rejected")):
        for item in package.get(section, []):
            gate = item.get("gate") or {}
            rows.append({
                "kind": item.get("kind") or ("figure" if item.get("is_figure") else "table"),
                "index": item.get("index"),
                "docling_item_ref": item.get("docling_item_ref"),
                "page_number": item.get("page_number"),
                "caption": item.get("caption"),
                "verdict": verdict,
                "why": item.get("why") or item.get("reason") or gate.get("reason"),
                "stage": item.get("stage"),
                "axis_label": gate.get("axis_label"),
                "axis_points": gate.get("axis_points"),
                "observation_count": len(item.get("observations") or []),
            })
    return sorted(rows, key=lambda row: (row["page_number"] or 0, row["index"] or 0))


def verdict_by_ref(package: dict) -> dict[str, dict]:
    """{docling_item_ref: {verdict, gate}} — what `docling_pipeline` writes onto assets."""
    return {
        row["docling_item_ref"]: row
        for row in decisions(package)
        if row.get("docling_item_ref")
    }
