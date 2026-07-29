"""Request and response models for the dataset and prediction surfaces."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DatasetSource(BaseModel):
    """What the project's scientific tables currently hold.

    Separated from the dataset itself so the client can tell an empty project apart from an
    unimplemented builder — the first is fixed by extracting more papers, the second is not
    fixable by the user at all.
    """

    experiments: int = 0
    ingredients: int = 0
    indicators: int = 0
    measurements: int = 0
    #: Indicators carrying a threshold. Without one, no survival label can be derived, so
    #: this is the count that decides whether a build could produce anything.
    indicators_with_threshold: int = 0


class DatasetPreview(BaseModel):
    """The project's flat, prediction-ready dataset — or the reason there isn't one."""

    project_id: int
    status: Literal["not_built", "not_implemented", "ready"] = "not_built"
    columns: list[str] = Field(default_factory=list)
    row_count: int = 0
    #: A head of the data, never the whole thing. The full dataset goes to the prediction
    #: service directly; this is for the screen.
    rows: list[dict[str, Any]] = Field(default_factory=list)
    source: DatasetSource = Field(default_factory=DatasetSource)


class JobAccepted(BaseModel):
    """The only thing a "start work" endpoint returns.

    Progress is followed through `GET /api/jobs/{job_id}/events`, the same stream the
    extraction workflows use; there is no per-workflow status endpoint to poll.
    """

    job_id: int
    status: str
