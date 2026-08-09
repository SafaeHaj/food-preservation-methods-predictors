"""Shared Celery factory.

Each service owns its own Celery app and task set -- extraction parses documents,
processing resolves them and builds datasets -- but they share one broker/result backend and
the same serialization settings, so the config lives here rather than being duplicated.

`processing.*` is wildcarded, so a new task named `processing.<x>` routes itself. The
extraction entry is enumerated because there is only one.
"""

import os

from celery import Celery


def make_celery(name: str) -> Celery:
    app = Celery(
        name,
        broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        worker_prefetch_multiplier=1,
    )

    app.conf.update(
        task_default_queue=name,
        task_default_exchange=name,
        task_default_exchange_type="direct",
        task_default_routing_key=name,
        task_routes={
            "extraction.workspace_extraction": {"queue": "extraction"},
            "processing.*": {"queue": "processing"},
        },
    )

    return app
