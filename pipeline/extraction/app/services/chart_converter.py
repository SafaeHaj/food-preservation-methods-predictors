"""
chart_converter.py — PP-Chart2Table wrapper with validation.

For every extracted figure PNG:
  1. Run PP-Chart2Table to get a Markdown table string.
  2. Parse the Markdown table to a pandas DataFrame.
  3. Validate the DataFrame — reject if it does not look like numeric chart data.
  4. Save the validated CSV alongside the original PNG.
  5. Record the result (valid / rejected / error) in FigureConversionCache.

Both the original PNG and the CSV (when valid) are preserved.
The CSV is NOT automatically the source of truth — it is approximate unless
the same value is confirmed in text or a native table.

Model loading is lazy and cached as a module-level singleton so the heavy
PP-Chart2Table weights are downloaded and loaded only once per process.
"""
import hashlib
import logging
import re
from io import StringIO
from pathlib import Path
from typing import Optional

import pandas as pd

from app.services.docling_extractor import DoclingFigure

logger = logging.getLogger(__name__)


# ─── Validation rules ─────────────────────────────────────────────────────────

# A valid chart CSV must have at least this many data rows (excluding header).
_MIN_ROWS = 2
# A valid chart CSV must have at least this many columns.
_MIN_COLS = 2
# Reject if there are more columns than this (likely a multi-panel confusion).
_MAX_COLS = 20


def _validate_dataframe(df: pd.DataFrame) -> tuple:
    """
    Decide whether a DataFrame produced by PP-Chart2Table is usable.

    Returns (valid: bool, reject_reason: str | None).
    """
    if df is None or df.empty:
        return False, "empty dataframe"
    if len(df) < _MIN_ROWS:
        return False, f"too few rows ({len(df)} < {_MIN_ROWS})"
    if len(df.columns) < _MIN_COLS:
        return False, f"too few columns ({len(df.columns)} < {_MIN_COLS})"
    if len(df.columns) > _MAX_COLS:
        return False, f"too many columns ({len(df.columns)} > {_MAX_COLS}) — likely multi-panel confusion"

    # At least one column must contain numeric values
    has_numeric = False
    for col in df.columns:
        try:
            numeric = pd.to_numeric(df[col], errors="coerce")
            if numeric.notna().any():
                has_numeric = True
                break
        except Exception:
            pass
    if not has_numeric:
        return False, "no numeric columns — likely a photograph or diagram, not a chart"

    # Reject if all cells are null/whitespace
    all_null = df.map(lambda v: v is None or (isinstance(v, str) and not v.strip())).all(axis=None)
    if all_null:
        return False, "all cells are null or whitespace"

    return True, None


def _parse_markdown_table(md_table: str) -> Optional[pd.DataFrame]:
    """
    Parse a Markdown pipe table produced by PP-Chart2Table.
    Drops the |---|---| alignment row that causes read_csv confusion.
    Returns None on failure.
    """
    if not md_table or not md_table.strip():
        return None
    try:
        lines = [ln for ln in md_table.splitlines() if ln.strip()]
        # Drop alignment row: a line whose non-pipe content is only dashes/colons/spaces
        kept = [
            ln for ln in lines
            if not re.match(r"^\s*\|?[\s\-:]+(\|[\s\-:]+)*\|?\s*$", ln)
        ]
        if len(kept) < 2:
            return None
        df = pd.read_csv(StringIO("\n".join(kept)), sep="|", engine="python")
        df = df.dropna(axis=1, how="all")
        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(how="all")
        # Strip whitespace from string columns
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].str.strip()
        return df if not df.empty else None
    except Exception as exc:
        logger.debug("Markdown table parse failed: %s", exc)
        return None


# ─── Model singleton ──────────────────────────────────────────────────────────

_chart_model = None
_chart_model_error: Optional[str] = None


def _get_chart_model():
    """Load PP-Chart2Table model once; return None if unavailable."""
    global _chart_model, _chart_model_error
    if _chart_model is not None:
        return _chart_model
    if _chart_model_error is not None:
        return None  # already tried and failed
    try:
        from paddleocr import ChartParsing
        import torch
        device = "gpu" if torch.cuda.is_available() else "cpu"
        dtype = "float16" if device == "gpu" else "float32"
        logger.info("Loading PP-Chart2Table model on %s …", device)
        _chart_model = ChartParsing(
            model_name="PP-Chart2Table",
            engine="transformers",
            engine_config={"dtype": dtype},
            device=device,
        )
        logger.info("PP-Chart2Table model loaded.")
        return _chart_model
    except Exception as exc:
        _chart_model_error = str(exc)
        logger.warning(
            "PP-Chart2Table not available (%s). Chart conversion will be skipped.", exc
        )
        return None


# ─── Result dataclass ─────────────────────────────────────────────────────────

from dataclasses import dataclass


@dataclass
class ChartResult:
    item_ref: str
    figure_index: int
    image_path: str
    image_hash: Optional[str]
    csv_path: Optional[str]          # None when rejected or on error
    status: str                      # 'valid' | 'rejected' | 'error' | 'skipped'
    reject_reason: Optional[str]
    row_count: int = 0
    col_count: int = 0


# ─── Main conversion entry point ──────────────────────────────────────────────

def _image_hash(image_path: str) -> Optional[str]:
    try:
        sha = hashlib.sha256()
        with open(image_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()
    except Exception:
        return None


def convert_charts(figures: list, cache_dir: str) -> list:
    """
    Convert all DoclingFigure PNGs with PP-Chart2Table and validate output.

    Parameters
    ----------
    figures  : list[DoclingFigure]   — figures from docling_extractor.extract_pdf()
    cache_dir: str                   — same cache dir as DoclingResult.cache_dir

    Returns list[ChartResult] — one per figure, with status valid/rejected/error/skipped.
    """
    model = _get_chart_model()
    results: list = []

    for idx, fig in enumerate(figures, start=1):
        if not fig.image_path or not Path(fig.image_path).exists():
            results.append(ChartResult(
                item_ref=fig.item_ref,
                figure_index=idx,
                image_path=fig.image_path,
                image_hash=None,
                csv_path=None,
                status="error",
                reject_reason="image file missing",
            ))
            continue

        img_hash = _image_hash(fig.image_path)

        # Check for existing CSV (cache hit by convention: same stem + _data.csv)
        img_p = Path(fig.image_path)
        csv_candidate = img_p.parent / f"{img_p.stem}_data.csv"
        if csv_candidate.exists():
            try:
                df = pd.read_csv(str(csv_candidate))
                valid, reason = _validate_dataframe(df)
                if valid:
                    results.append(ChartResult(
                        item_ref=fig.item_ref,
                        figure_index=idx,
                        image_path=fig.image_path,
                        image_hash=img_hash,
                        csv_path=str(csv_candidate),
                        status="valid",
                        reject_reason=None,
                        row_count=len(df),
                        col_count=len(df.columns),
                    ))
                    continue
                # Cached CSV was invalid — re-run or mark rejected
            except Exception:
                pass  # Corrupt cached CSV — re-run below

        if model is None:
            results.append(ChartResult(
                item_ref=fig.item_ref,
                figure_index=idx,
                image_path=fig.image_path,
                image_hash=img_hash,
                csv_path=None,
                status="skipped",
                reject_reason="PP-Chart2Table not installed",
            ))
            continue

        logger.info("Converting chart %d/%d: %s", idx, len(figures), img_p.name)
        try:
            pred_iter = model.predict(input={"image": str(img_p)}, batch_size=1)
            res = next(iter(pred_iter))
            md_table = res.get("result", "")

            df = _parse_markdown_table(md_table)
            if df is None:
                results.append(ChartResult(
                    item_ref=fig.item_ref,
                    figure_index=idx,
                    image_path=fig.image_path,
                    image_hash=img_hash,
                    csv_path=None,
                    status="rejected",
                    reject_reason="markdown table parse failed",
                ))
                continue

            valid, reason = _validate_dataframe(df)
            if not valid:
                results.append(ChartResult(
                    item_ref=fig.item_ref,
                    figure_index=idx,
                    image_path=fig.image_path,
                    image_hash=img_hash,
                    csv_path=None,
                    status="rejected",
                    reject_reason=reason,
                ))
                continue

            # Save validated CSV
            csv_path = img_p.parent / f"{img_p.stem}_data.csv"
            df.to_csv(str(csv_path), index=False)
            results.append(ChartResult(
                item_ref=fig.item_ref,
                figure_index=idx,
                image_path=fig.image_path,
                image_hash=img_hash,
                csv_path=str(csv_path),
                status="valid",
                reject_reason=None,
                row_count=len(df),
                col_count=len(df.columns),
            ))

        except Exception as exc:
            logger.warning("Chart conversion error for %s: %s", img_p.name, exc)
            results.append(ChartResult(
                item_ref=fig.item_ref,
                figure_index=idx,
                image_path=fig.image_path,
                image_hash=img_hash,
                csv_path=None,
                status="error",
                reject_reason=str(exc)[:200],
            ))

    valid_count = sum(1 for r in results if r.status == "valid")
    rejected_count = sum(1 for r in results if r.status == "rejected")
    logger.info(
        "Chart conversion: %d valid, %d rejected, %d error/skipped",
        valid_count, rejected_count, len(results) - valid_count - rejected_count,
    )
    return results
