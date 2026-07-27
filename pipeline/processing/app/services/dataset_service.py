"""Training-dataset upload, parsing, column mapping and retrieval."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import pandas as pd
from sqlalchemy.orm import Session

from shared.config import get_processing_settings
from shared.db.models import UploadedDataset
from shared.errors import NotFoundError, ValidationError
from shared.uow import unit_of_work

from app.repositories import model_lab_repo
from app.schemas.model_lab import DatasetOut, DatasetUploadOut, MappingUpdate

logger = logging.getLogger(__name__)
_settings = get_processing_settings()

CSV_SUFFIX = ".csv"
ALLOWED_SUFFIXES = {CSV_SUFFIX, ".xlsx", ".xls"}

#: Values that read as booleans regardless of how the source spelled them.
BOOLEAN_TOKENS = frozenset({"0", "1", "true", "false", "yes", "no"})


@dataclass(frozen=True)
class ParsedFile:
    headers: list[str]
    column_types: dict[str, str]
    row_count: int
    col_count: int
    sheet: str | None


def _is_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _infer_column_type(values: list[str]) -> str:
    non_empty = [value for value in values if value.strip()]
    if not non_empty:
        return "text"
    if all(value.lower() in BOOLEAN_TOKENS for value in non_empty):
        return "boolean"
    numeric = sum(1 for value in non_empty if _is_numeric(value))
    if numeric / len(non_empty) >= _settings.NUMERIC_COLUMN_THRESHOLD:
        return "numeric"
    distinct = len(set(non_empty))
    # Categorical needs both few distinct values and repetition; a 20-row file with 20
    # unique names would otherwise be called categorical.
    if distinct <= _settings.CATEGORICAL_MAX_DISTINCT and distinct <= len(non_empty) * 0.5:
        return "categorical"
    return "text"


def read_frame(path: Path, original_name: str, *, preview: bool) -> tuple[pd.DataFrame, str | None]:
    """Read a CSV or the first sheet of a workbook, as strings.

    `dtype=str` with `keep_default_na=False` is deliberate: this data is user-supplied and
    the column mapping decides what is numeric, so pandas must not silently coerce "N/A",
    "1,5" or a leading-zero identifier on the way in.
    """
    rows = _settings.DATASET_PREVIEW_ROWS if preview else None
    try:
        if original_name.lower().endswith(CSV_SUFFIX):
            return pd.read_csv(path, dtype=str, nrows=rows, keep_default_na=False), None
        sheet = pd.ExcelFile(path).sheet_names[0]
        frame = pd.read_excel(
            path, sheet_name=sheet, dtype=str, nrows=rows, keep_default_na=False
        )
        return frame, sheet
    except Exception as exc:
        raise ValidationError(
            "That file could not be read as a dataset",
            details={"filename": original_name, "reason": str(exc)},
        ) from exc


def parse(path: Path, original_name: str) -> ParsedFile:
    """Infer headers, types and shape. Raises `ValidationError` on an unreadable file.

    Previously returned `{"error": ...}`, which callers had to remember to check -- and the
    upload endpoint did check, but stored the dataset as "ready" anyway when other keys
    were missing.
    """
    frame, sheet = read_frame(path, original_name, preview=True)
    headers = [str(column) for column in frame.columns]
    return ParsedFile(
        headers=headers,
        column_types={
            str(column): _infer_column_type(frame[column].dropna().tolist())
            for column in frame.columns
        },
        row_count=len(frame),
        col_count=len(headers),
        sheet=sheet,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_settings.FILE_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_out(dataset: UploadedDataset) -> DatasetOut:
    return DatasetOut(
        id=dataset.id,
        project_id=dataset.project_id,
        original_name=dataset.original_name,
        dataset_family=dataset.dataset_family,
        row_count=dataset.row_count or 0,
        col_count=dataset.col_count or 0,
        headers=json.loads(dataset.headers_json or "[]"),
        column_types=json.loads(dataset.column_types_json or "{}"),
        column_mapping=json.loads(dataset.column_mapping_json or "{}"),
        parse_status=dataset.parse_status,
        parse_error=dataset.parse_error,
        file_hash=dataset.file_hash,
        sheet_name=dataset.sheet_name,
        uploaded_at=dataset.uploaded_at,
        updated_at=dataset.updated_at,
    )


def list_datasets(db: Session, project_id: int) -> list[DatasetOut]:
    return [to_out(dataset) for dataset in model_lab_repo.active_datasets(db, project_id)]


def require_dataset(db: Session, project_id: int, dataset_id: int) -> UploadedDataset:
    dataset = model_lab_repo.get_dataset(db, project_id, dataset_id)
    if not dataset:
        raise NotFoundError.for_resource("Dataset", dataset_id)
    return dataset


def get_dataset(db: Session, project_id: int, dataset_id: int) -> DatasetOut:
    return to_out(require_dataset(db, project_id, dataset_id))


def _storage_dir(project_id: int) -> Path:
    directory = _settings.dataset_path / str(project_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def upload(
    db: Session, project_id: int, uploader_id: int, *,
    filename: str, stream: BinaryIO, family: str, force_replace: bool,
) -> DatasetUploadOut:
    """Store an uploaded dataset, deduplicating by content hash within the project."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValidationError(
            f"'{suffix or filename}' is not a supported dataset format",
            details={"allowed": sorted(ALLOWED_SUFFIXES)},
        )

    destination = _storage_dir(project_id) / f"{uuid.uuid4().hex}{suffix}"
    with destination.open("wb") as handle:
        while chunk := stream.read(_settings.FILE_CHUNK_BYTES):
            handle.write(chunk)

    file_hash = _sha256(destination)
    duplicate = model_lab_repo.find_duplicate(db, project_id, file_hash, family)
    if duplicate and not force_replace:
        destination.unlink(missing_ok=True)
        return DatasetUploadOut(
            duplicate=True,
            dataset=to_out(duplicate),
            message=(
                "A dataset with identical content already exists for this project. "
                "Upload again with force_replace to keep both."
            ),
        )

    try:
        parsed = parse(destination, filename)
    except ValidationError:
        # Do not persist a row pointing at a file we could not read: it would appear in the
        # dataset list as selectable and fail only at train time.
        destination.unlink(missing_ok=True)
        raise

    with unit_of_work(db):
        superseded = model_lab_repo.active_of_family(db, project_id, family)
        if superseded:
            # Soft delete: training runs reference it, and their history must stay readable.
            superseded.is_active = False

        dataset = UploadedDataset(
            project_id=project_id,
            uploader_id=uploader_id,
            original_name=filename,
            filename=destination.name,
            file_path=str(destination),
            file_hash=file_hash,
            dataset_family=family,
            sheet_name=parsed.sheet,
            row_count=parsed.row_count,
            col_count=parsed.col_count,
            headers_json=json.dumps(parsed.headers),
            column_types_json=json.dumps(parsed.column_types),
            column_mapping_json="{}",
            parse_status="ready",
            is_active=True,
        )
        db.add(dataset)

    db.refresh(dataset)
    return DatasetUploadOut(duplicate=False, dataset=to_out(dataset))


def update_mapping(
    db: Session, project_id: int, dataset_id: int, body: MappingUpdate
) -> DatasetOut:
    dataset = require_dataset(db, project_id, dataset_id)
    headers = set(json.loads(dataset.headers_json or "[]"))
    unknown = sorted(set(body.column_mapping.values()) - headers - {""})
    if unknown:
        raise ValidationError(
            "The mapping refers to columns that are not in this dataset",
            details={"unknown_columns": unknown, "available": sorted(headers)},
        )

    with unit_of_work(db):
        dataset.column_mapping_json = json.dumps(body.column_mapping)
        if body.dataset_family:
            dataset.dataset_family = body.dataset_family
        dataset.updated_at = datetime.utcnow()

    db.refresh(dataset)
    return to_out(dataset)


def deactivate(db: Session, project_id: int, dataset_id: int) -> None:
    dataset = require_dataset(db, project_id, dataset_id)
    with unit_of_work(db):
        dataset.is_active = False


def file_for_download(db: Session, project_id: int, dataset_id: int) -> tuple[Path, str]:
    dataset = require_dataset(db, project_id, dataset_id)
    path = Path(dataset.file_path)
    if not path.exists():
        raise NotFoundError("The stored file for this dataset is missing")
    return path, dataset.original_name
