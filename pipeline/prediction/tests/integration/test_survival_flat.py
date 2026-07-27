"""Contract test for the flat-table survival endpoints.

Exercises POST /api/v1/survival/train + /predict against a synthetic dataset in the exact
column/role shape the frontend's model-lab upload produces (see columnRoles.ts
SURVIVAL_TEMPLATE_ROWS). Asserts the result dict matches what the BFF's _bg_train / predict
already consume. RSF/GBS legitimately report "skipped" when scikit-survival / xgboost are
absent; weibull_aft (scipy-only, R stage-2 optional) must complete.
"""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

os.environ["SURVIVAL_ARTIFACT_DIR"] = tempfile.mkdtemp(prefix="survival_artifacts_")

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

FEATURE_ROLES = {
    "time_days": "time",
    "event": "event",
    "temperature_C": "temperature",
    "pH": "pH",
    "aw": "aw",
    "preservative": "preservative",
    "concentration_ppm": "concentration",
    "packaging": "packaging",
    "product_category": "product_category",
}


def _synthetic_records(n: int = 48, seed: int = 0) -> list[dict]:
    rng = np.random.default_rng(seed)
    preservatives = ["nisin", "natamycin", "control"]
    packagings = ["MAP", "Air", "vacuum"]
    categories = ["cheese", "meat"]
    records = []
    for _ in range(n):
        pres = rng.choice(preservatives)
        conc = 0.0 if pres == "control" else float(rng.uniform(1.0, 6.0))
        temp = float(rng.choice([4.0, 10.0]))
        ph = float(rng.uniform(5.5, 6.5))
        aw = float(rng.uniform(0.94, 0.98))
        # longer shelf life for more preservative and colder storage, plus noise
        log_t = 2.4 + 0.10 * conc - 0.06 * (temp - 4.0) + rng.normal(0, 0.25)
        t_true = float(np.exp(log_t))
        censor = float(rng.uniform(10.0, 40.0))
        t_obs = min(t_true, censor)
        event = int(t_true <= censor)
        records.append({
            "time_days": round(t_obs, 2),
            "event": event,
            "temperature_C": temp,
            "pH": round(ph, 2),
            "aw": round(aw, 3),
            "preservative": pres,
            "concentration_ppm": round(conc, 2),
            "packaging": str(rng.choice(packagings)),
            "product_category": str(rng.choice(categories)),
        })
    return records


def test_train_then_predict_contract():
    records = _synthetic_records()
    resp = client.post("/api/v1/survival/train", json={"records": records, "mapping": FEATURE_ROLES})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert "error" not in body, body
    assert body["time_col"] == "time_days"
    assert body["event_col"] == "event"
    assert isinstance(body["feature_cols"], list) and body["feature_cols"]

    models = body["models"]
    assert set(models) == {"weibull_aft", "rsf", "gbs"}, models
    for name, m in models.items():
        assert m["status"] in {"completed", "skipped", "failed"}, (name, m)
        if m["status"] != "completed":
            assert m.get("reason"), (name, m)

    waft = models["weibull_aft"]
    assert waft["status"] == "completed", waft
    assert waft["n_train"] == body["n_rows"]
    assert "artifact_path" in waft and waft["artifact_path"]

    # predict from the persisted Weibull artifact
    features = {
        "temperature_C": 4.0, "pH": 6.1, "aw": 0.96,
        "preservative": "nisin", "concentration_ppm": 4.0,
        "packaging": "MAP", "product_category": "cheese",
    }
    presp = client.post("/api/v1/survival/predict", json={
        "model_ref": waft["artifact_path"],
        "model_name": "weibull_aft",
        "input_features": features,
        "required_shelf_life": 14.0,
    })
    assert presp.status_code == 200, presp.text
    pred = presp.json()
    assert "error" not in pred, pred
    assert pred["model_name"] == "weibull_aft"
    for key in ("predicted_shelf_life_days", "ci_lo_days", "ci_hi_days"):
        assert isinstance(pred[key], (int, float)), pred
    assert pred["predicted_shelf_life_days"] > 0
    assert pred["ci_lo_days"] <= pred["ci_hi_days"]
    assert pred["required_shelf_life_days"] == 14.0
    assert isinstance(pred["success"], bool)


def test_missing_time_role_returns_error():
    records = _synthetic_records(n=12)
    bad_mapping = {k: v for k, v in FEATURE_ROLES.items() if v != "time"}
    resp = client.post("/api/v1/survival/train", json={"records": records, "mapping": bad_mapping})
    assert resp.status_code == 200, resp.text
    assert "error" in resp.json()


def test_predict_unknown_artifact_returns_error():
    resp = client.post("/api/v1/survival/predict", json={
        "model_ref": "weibull_aft_deadbeef", "model_name": "weibull_aft", "input_features": {},
    })
    assert resp.status_code == 200
    assert "error" in resp.json()
