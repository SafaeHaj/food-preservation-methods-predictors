"""Threshold crossing computation for the shelf-life analysis page."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from shared.db.models import ThresholdDefinition


def compute_crossings(threshold: "ThresholdDefinition", project_id: int, db: "Session") -> list[dict[str, Any]]:
    """
    For each trajectory in the project matching the threshold's measurement_type,
    estimate the time when the threshold is first crossed.

    Returns a list of crossing records.
    """
    from shared.db.models import (
        Experiment, ModelFit, ModelPrediction, ModelRun,
        Observation, TrajectoryDefinition, TreatmentArm, Study,
    )
    from shared.db.models import Microorganism

    import json

    trajectories = (
        db.query(TrajectoryDefinition)
          .filter(
              TrajectoryDefinition.project_id == project_id,
              TrajectoryDefinition.measurement_type == threshold.measurement_type,
          ).all()
    )

    op = threshold.comparison_operator
    limit = threshold.threshold_value

    results = []

    for traj in trajectories:
        obs_ids = traj.observation_ids
        if not obs_ids:
            continue

        obs_list = (
            db.query(Observation)
              .filter(Observation.id.in_(obs_ids))
              .order_by(Observation.time_days)
              .all()
        )
        t_vals = np.array([o.time_days for o in obs_list if o.time_days is not None], dtype=float)
        y_vals = np.array(
            [o.numeric_value_normalized for o in obs_list
             if o.time_days is not None and o.numeric_value_normalized is not None],
            dtype=float,
        )

        crossing_day: float | None = None
        source = "observed"

        # Try observed data first
        for t, y in zip(t_vals, y_vals):
            if _crossed(y, limit, op):
                crossing_day = float(t)
                break

        # If not crossed in observed data, try best model predictions
        if crossing_day is None:
            best_run = (
                db.query(ModelRun)
                  .filter(ModelRun.trajectory_id == traj.id, ModelRun.status == "completed")
                  .order_by(ModelRun.created_at.desc())
                  .first()
            )
            if best_run and best_run.selected_model_id:
                preds = (
                    db.query(ModelPrediction)
                      .filter(ModelPrediction.fit_id == best_run.selected_model_id)
                      .order_by(ModelPrediction.time_days)
                      .all()
                )
                for pred in preds:
                    if pred.predicted_value is not None and _crossed(pred.predicted_value, limit, op):
                        crossing_day = float(pred.time_days)
                        source = "model_predicted"
                        break

        results.append({
            "trajectory_id": traj.id,
            "trajectory_label": traj.label,
            "treatment_arm_id": traj.treatment_arm_id,
            "n_observations": len(t_vals),
            "time_min_days": float(t_vals.min()) if len(t_vals) else None,
            "time_max_days": float(t_vals.max()) if len(t_vals) else None,
            "threshold_crossed": crossing_day is not None,
            "crossing_day": crossing_day,
            "source": source,
        })

    return results


def _crossed(value: float, limit: float, op: str) -> bool:
    ops = {
        "<=": value <= limit,
        ">=": value >= limit,
        "<": value < limit,
        ">": value > limit,
        "==": abs(value - limit) < 1e-9,
    }
    return ops.get(op, False)
