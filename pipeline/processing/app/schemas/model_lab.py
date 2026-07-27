"""Model-lab request and response models.

Replaces the hand-built dicts (`_dataset_to_dict`, `_run_to_dict`, `_result_to_dict`) that
lived in the route module and were the de-facto API contract without ever being declared.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class DatasetOut(BaseModel):
    id: int
    project_id: int
    original_name: str
    dataset_family: Optional[str] = None
    row_count: int = 0
    col_count: int = 0
    headers: list[str] = []
    column_types: dict[str, str] = {}
    column_mapping: dict[str, str] = {}
    parse_status: str
    parse_error: Optional[str] = None
    file_hash: Optional[str] = None
    sheet_name: Optional[str] = None
    uploaded_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DatasetUploadOut(BaseModel):
    duplicate: bool
    dataset: DatasetOut
    message: Optional[str] = None


class MappingUpdate(BaseModel):
    column_mapping: dict[str, str]
    dataset_family: Optional[str] = None


class ModelResultOut(BaseModel):
    id: int
    training_run_id: int
    model_name: str
    model_family: str
    status: str
    skip_reason: Optional[str] = None
    error_message: Optional[str] = None
    metrics: dict[str, Any] = {}
    parameters: dict[str, Any] = {}
    feature_cols: list[str] = []
    target_col: Optional[str] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None
    r_squared: Optional[float] = None
    concordance_index: Optional[float] = None
    has_artifact: bool = False
    is_active: bool = True
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    #: Full per-trajectory fits; only populated on the single-model endpoint for kinetic
    #: families, because it can be megabytes and would bloat every list response.
    results: Optional[dict[str, Any]] = None


class JobSummary(BaseModel):
    status: str
    progress: int = 0
    current_step: str = ""
    error_message: Optional[str] = None


class TrainingRunOut(BaseModel):
    id: int
    project_id: int
    dataset_id: int
    dataset_name: Optional[str] = None
    job_id: Optional[int] = None
    dataset_family: str
    n_trajectories: int = 0
    n_fitted: int = 0
    status: str
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    model_results: list[ModelResultOut] = []
    job: Optional[JobSummary] = None


class TrainRequest(BaseModel):
    dataset_id: int
    column_mapping: dict[str, str]
    dataset_family: str
    #: log10 threshold defining failure for kinetic time-to-failure derivation.
    threshold: Optional[float] = None


class TrainingAccepted(BaseModel):
    training_run_id: int
    job_id: int
    status: str


class PredictRequest(BaseModel):
    model_id: int
    input_features: dict[str, Any] = Field(default_factory=dict)
    required_shelf_life: Optional[float] = None
    #: ISO date; when given, the response carries the expected spoilage date.
    start_date: Optional[str] = None


class PredictionOut(BaseModel):
    model_name: str
    predicted_shelf_life_days: float
    ci_lo_days: Optional[float] = None
    ci_hi_days: Optional[float] = None
    required_shelf_life_days: Optional[float] = None
    success: Optional[bool] = None
    p_success: Optional[float] = None
    expected_spoilage_date: Optional[str] = None
