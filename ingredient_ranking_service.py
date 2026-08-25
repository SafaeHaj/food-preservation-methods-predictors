"""
ingredient_ranking_service.py -- loads artifacts_ingredient_ranking/
(produced by train_ingredient_ranking.py) and serves the precomputed
ingredient efficacy ranking. There is nothing to "predict" here: the ranking
is a fixed table built once from the training data, so this service is a
thin read-only lookup, not a model-serving class like ModelService or
ClassificationService.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = ROOT / "artifacts_ingredient_ranking"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class IngredientRankingService:
    def __init__(self) -> None:
        self.rankings: list[dict[str, Any]] = _read_json(ARTIFACTS_DIR / "ingredient_rankings.json")
        self.class_definitions: dict[str, Any] = _read_json(ARTIFACTS_DIR / "class_definitions.json")
        self.manifest: dict[str, Any] = _read_json(ARTIFACTS_DIR / "training_manifest.json")
        self._by_name: dict[str, dict[str, Any]] = {r["ingredient_name"]: r for r in self.rankings}

    def get(self, name: str) -> dict[str, Any] | None:
        return self._by_name.get(name)

    @property
    def families(self) -> list[str]:
        return sorted({r["ingredient_family"] for r in self.rankings})
