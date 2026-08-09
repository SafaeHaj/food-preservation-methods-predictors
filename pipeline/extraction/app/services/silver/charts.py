"""Reading a chart image back into a table, in batches, with a cache.

PP-Chart2Table is the most expensive step per figure and the only one that needs a GPU, so
five things matter here and nowhere else in Silver:

  * figures go to the model in batches, not one at a time;
  * a result is cached on the image's own digest, so a re-queued paper pays once;
  * an out-of-memory error halves the batch and retries rather than losing the paper —
    VRAM is the real ceiling, and one oversized figure should not cost the other seven;
  * the model is shown a bounded copy of each figure, because its cost follows the pixel
    count it is given while the archived PNG keeps its full resolution;
  * decoding is bounded, because chart-to-table is long-output autoregressive generation
    and an unreadable figure otherwise decodes until the model stops itself.

The model itself is loaded by `chart_converter`, which owns the singleton. This module owns
*how it is called*; the returned rows go straight to the schema gate, which decides whether
what came back is a series or a hallucinated table.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Optional, Sequence

from PIL import Image

from shared.config import get_extraction_settings

from app.services.chart_converter import _get_chart_model, _parse_markdown_table

logger = logging.getLogger(__name__)
_settings = get_extraction_settings()

CHART_MODEL_VERSION = "pp-chart2table-1"

_OOM_MARKERS = ("out of memory", "cuda error", "cublas", "alloc failed", "resource exhausted")


def _result(status: str, **extra) -> dict:
    return {"status": status, "headers": [], "rows": [], **extra}


def _image_digest(image_path: str) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with open(image_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_settings.FILE_CHUNK_BYTES), b""):
                digest.update(chunk)
        return digest.hexdigest()[:32]
    except OSError:
        return None


def _cache_path(digest: str) -> Path:
    """Keyed on the bounds as well as the image: the same figure shown at a different size
    or given a different decode budget is a different question, and a key that ignored
    them would keep answering the old one after the settings changed."""
    directory = _settings.chart_cache_path / CHART_MODEL_VERSION
    directory.mkdir(parents=True, exist_ok=True)
    return directory / (f"{digest}-{_settings.CHART_MAX_PIXELS}"
                        f"-{_settings.CHART_MAX_NEW_TOKENS}.json")


def _load_cached(digest: Optional[str]) -> Optional[dict]:
    if not digest:
        return None
    path = _cache_path(digest)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _store_cached(digest: Optional[str], result: dict) -> None:
    if not digest or result["status"] not in ("converted", "unreadable"):
        return
    try:
        _cache_path(digest).write_text(
            json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8"
        )
    except OSError:
        logger.warning("Could not cache the chart conversion for %s", digest, exc_info=True)


def _is_out_of_memory(exc: BaseException) -> bool:
    message = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in message for marker in _OOM_MARKERS)


def _bounded_inputs(image_paths: Sequence[str], workdir: Path) -> list[str]:
    """Copies of the figures bounded to CHART_MAX_PIXELS, positionally aligned with the
    input. The model tiles what it is shown, so its cost follows the pixel count; the
    archived PNG keeps its full IMAGES_SCALE resolution. A figure already inside the bound
    is passed through untouched, which for most figures makes this a no-op.
    """
    max_side = max(1, _settings.CHART_MAX_PIXELS)
    prepared = []
    for path in image_paths:
        try:
            with Image.open(path) as opened:
                opened.load()
                if max(opened.size) <= max_side:
                    prepared.append(str(path))
                    continue
                scale = max_side / max(opened.size)
                resized = opened.convert("RGB").resize(
                    (max(1, int(opened.width * scale)), max(1, int(opened.height * scale))),
                    Image.LANCZOS)
            target = workdir / f"{Path(path).stem}_{max_side}.png"
            resized.save(target)
            prepared.append(str(target))
        except (OSError, ValueError):
            # An unreadable figure is the gate's problem, not this function's: hand the
            # original over and let the model call produce the error record.
            prepared.append(str(path))
    return prepared


#: Which generation-bound keyword this paddleocr build accepts, found once on the first
#: call. `None` until then; `{}` once both have been rejected.
_predict_kwargs: Optional[dict] = None


def _bounded_predict(model, payload: list[dict], batch_size: int) -> list:
    """One `predict` call with decoding bounded, whichever keyword this build takes.

    The keyword moved between paddleocr releases, so the first call finds the one that
    works and every call after goes straight to it.
    """
    global _predict_kwargs
    if _predict_kwargs is not None:
        return list(model.predict(input=payload, batch_size=batch_size, **_predict_kwargs))

    for kwargs in ({"max_new_tokens": _settings.CHART_MAX_NEW_TOKENS},
                   {"max_length": _settings.CHART_MAX_NEW_TOKENS}):
        try:
            outputs = list(model.predict(input=payload, batch_size=batch_size, **kwargs))
        except TypeError:
            continue
        _predict_kwargs = kwargs
        logger.info("Chart generation bounded by %s=%d",
                    next(iter(kwargs)), _settings.CHART_MAX_NEW_TOKENS)
        return outputs

    _predict_kwargs = {}
    logger.warning("This paddleocr build accepts no generation bound on predict(); "
                   "chart decoding is unbounded")
    return list(model.predict(input=payload, batch_size=batch_size))


def _predict(model, paths: Sequence[str]) -> list[dict]:
    """One model call over a batch. Returns one result per path, positionally."""
    outputs = _bounded_predict(model, [{"image": path} for path in paths], len(paths))
    results = []
    for path, output in zip(paths, outputs):
        text = ""
        if isinstance(output, dict):
            text = output.get("result") or output.get("rec_text") or ""
        else:
            text = getattr(output, "result", "") or str(output)
        frame = _parse_markdown_table(text) if text else None
        if frame is None or frame.empty:
            results.append(_result("unreadable", error="the model returned no table"))
            continue
        results.append(_result(
            "converted",
            headers=[str(name) for name in frame.columns],
            rows=[[None if value is None else str(value) for value in row]
                  for row in frame.itertuples(index=False, name=None)],
        ))
    # A model that returns fewer outputs than inputs would silently shift every result
    # onto the wrong figure, so the shortfall is filled rather than zipped away.
    results.extend(_result("unreadable", error="the model returned no output")
                   for _ in range(len(paths) - len(results)))
    return results


def _convert_batch(model, paths: Sequence[str]) -> list[dict]:
    """Predict, halving the batch on an out-of-memory error down to a single figure."""
    if not paths:
        return []
    try:
        return _predict(model, paths)
    except Exception as exc:
        if not _is_out_of_memory(exc) or len(paths) == 1:
            reason = f"{type(exc).__name__}: {exc}"
            logger.warning("Chart conversion failed for %d figure(s): %s", len(paths), reason)
            return [_result("error", error=reason) for _ in paths]
        middle = len(paths) // 2
        logger.info("Out of memory on %d figures; halving the batch", len(paths))
        return _convert_batch(model, paths[:middle]) + _convert_batch(model, paths[middle:])


def convert_figures(image_paths: Sequence[str]) -> list[dict]:
    """Convert every image, in order. One result per input, always.

    `unavailable` is distinct from `error`: the first means no chart model is installed in
    this deployment, which `REQUIRE_FIGURE_DATA=0` deliberately tolerates, and the second
    means one was there and could not read this figure.
    """
    if not image_paths:
        return []

    digests = [_image_digest(path) for path in image_paths]
    results: list[Optional[dict]] = [_load_cached(digest) for digest in digests]
    pending = [index for index, result in enumerate(results) if result is None]
    if not pending:
        logger.info("All %d figure conversions reused from cache", len(image_paths))
        return [result for result in results if result is not None]

    model = _get_chart_model()
    if model is None:
        from app.services.chart_converter import _chart_model_error
        unavailable = _result("unavailable", error=_chart_model_error or "no chart model")
        for index in pending:
            results[index] = unavailable
        return [result for result in results if result is not None]

    batch_size = max(1, _settings.CHART_BATCH_SIZE)
    # The bounded copies are model input, not an artifact, so they live and die with the
    # call rather than being written next to the figures they stand in for.
    with tempfile.TemporaryDirectory(prefix="chart_inputs_") as scratch:
        bounded = _bounded_inputs([image_paths[index] for index in pending], Path(scratch))
        for start in range(0, len(pending), batch_size):
            indexes = pending[start:start + batch_size]
            converted = _convert_batch(model, bounded[start:start + batch_size])
            for index, result in zip(indexes, converted):
                results[index] = result
                _store_cached(digests[index], result)

    logger.info(
        "Converted %d figure(s), %d reused from cache",
        len(pending), len(image_paths) - len(pending),
    )
    return [result if result is not None else _result("error", error="not converted")
            for result in results]
