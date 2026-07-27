"""Prediction against a trained model-lab model."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from shared.db.models import LabModelResult
from shared.errors import BusinessRuleError, NotFoundError, ValidationError

from app.repositories import model_lab_repo
from app.schemas.model_lab import ModelResultOut, PredictRequest, PredictionOut
from app.services.training_service import KINETIC, result_to_out

logger = logging.getLogger(__name__)


def list_models(db: Session, project_id: int) -> list[ModelResultOut]:
    return [result_to_out(model) for model in model_lab_repo.active_models(db, project_id)]


def get_model(db: Session, project_id: int, model_id: int) -> ModelResultOut:
    model = model_lab_repo.get_model(db, project_id, model_id)
    if not model:
        raise NotFoundError.for_resource("Model", model_id)
    # Per-trajectory fits are only meaningful for kinetic models, and large enough that
    # returning them in list responses would dominate the payload.
    return result_to_out(model, include_results=model.model_family == KINETIC)


def deactivate_model(db: Session, project_id: int, model_id: int) -> None:
    from shared.uow import unit_of_work

    model = model_lab_repo.get_model(db, project_id, model_id)
    if not model:
        raise NotFoundError.for_resource("Model", model_id)
    with unit_of_work(db):
        model.is_active = False


def _require_predictable(db: Session, project_id: int, model_id: int) -> LabModelResult:
    model = model_lab_repo.get_model(db, project_id, model_id, active_only=True)
    if not model:
        raise NotFoundError.for_resource("Model", model_id)
    if model.status != "completed":
        raise BusinessRuleError(
            f"This model is not trained (status: {model.status})",
            details={"model_id": model_id, "status": model.status},
        )
    if model.model_family == KINETIC:
        raise BusinessRuleError(
            "Kinetic models are fitted per trajectory and cannot be queried with a "
            "single formulation. View the fitted curves in the model registry instead."
        )
    if not model.artifact_path:
        raise BusinessRuleError(
            "This model has no saved artifact; retrain it before predicting"
        )
    return model


def predict(db: Session, project_id: int, body: PredictRequest) -> PredictionOut:
    from app.services.survival_trainer import predict_survival

    model = _require_predictable(db, project_id, body.model_id)

    result = predict_survival(
        artifact_path=model.artifact_path,
        model_name=model.model_name,
        input_features=body.input_features,
        required_shelf_life=body.required_shelf_life,
    )

    prediction = PredictionOut(
        model_name=result.get("model_name", model.model_name),
        predicted_shelf_life_days=result["predicted_shelf_life_days"],
        ci_lo_days=result.get("ci_lo_days"),
        ci_hi_days=result.get("ci_hi_days"),
        required_shelf_life_days=result.get("required_shelf_life_days"),
        success=result.get("success"),
        p_success=result.get("p_success"),
    )

    if body.start_date:
        try:
            start = date.fromisoformat(body.start_date)
        except ValueError:
            raise ValidationError(
                "start_date must be an ISO date (YYYY-MM-DD)",
                details={"received": body.start_date},
            )
        prediction.expected_spoilage_date = (
            start + timedelta(days=prediction.predicted_shelf_life_days)
        ).isoformat()

    return prediction
