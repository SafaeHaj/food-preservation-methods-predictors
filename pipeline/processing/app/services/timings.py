"""Where a paper's extraction time went.

One collector per Celery task, held in a context variable rather than a module global: two
papers run in the same worker process under `--concurrency=2`, and a module-level list
would interleave their measurements into something neither of them can be billed for.

The numbers land on `Job.result["timings"]`, which is the row the UI already polls. Sizing
`OLLAMA_NUM_CTX` or a prompt budget from habit is how three papers were lost to a
`num_predict` guess; `prompt_eval_count` and `eval_count` are recorded here so it can be
sized from data instead.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Optional

_collector: ContextVar[Optional[list[dict]]] = ContextVar("extraction_timings", default=None)


@contextmanager
def collect() -> Iterator[list[dict]]:
    """Scope a run's metrics. Everything recorded inside lands in the yielded list."""
    records: list[dict] = []
    token = _collector.set(records)
    try:
        yield records
    finally:
        _collector.reset(token)


def record_metric(stage: str, paper: Optional[str] = None, **fields: Any) -> None:
    """Record one measurement. A no-op outside `collect()`, so services stay callable
    from a script or a test without a scope to write into."""
    records = _collector.get()
    if records is not None:
        records.append({"stage": stage, "paper": paper, **fields})


@contextmanager
def stage_timer(stage: str, paper: Optional[str] = None, **fields: Any) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        record_metric(stage, paper, seconds=round(time.perf_counter() - started, 3), **fields)


def totals(records: list[dict]) -> dict[str, dict[str, float]]:
    """{stage: {seconds, calls}} — the summary worth putting on a job row."""
    summary: dict[str, dict[str, float]] = {}
    for record in records:
        entry = summary.setdefault(record["stage"], {"seconds": 0.0, "calls": 0})
        entry["seconds"] = round(entry["seconds"] + (record.get("seconds") or 0.0), 3)
        entry["calls"] += 1
    return summary
