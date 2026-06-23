"""Scientific validation rules for food-preservation data."""
from typing import Any, Dict, List, Tuple


SCIENTIFIC_RULES = [
    {
        "field_patterns": ["concentration", "conc"],
        "rule": "Concentration must be >= 0",
        "check": lambda v: float(v) >= 0,
    },
    {
        "field_patterns": ["day", "time", "duration"],
        "rule": "Time/day must be >= 0",
        "check": lambda v: float(v) >= 0,
    },
    {
        "field_patterns": ["ph"],
        "rule": "pH must be between 3.0 and 8.5",
        "check": lambda v: 3.0 <= float(v) <= 8.5,
    },
    {
        "field_patterns": ["log_cfu", "cfu"],
        "rule": "Log CFU/g must be between 0 and 12",
        "check": lambda v: 0.0 <= float(v) <= 12.0,
    },
    {
        "field_patterns": ["percent", "pct", "humidity", "moisture"],
        "rule": "Percentage must be between 0 and 100",
        "check": lambda v: 0.0 <= float(v) <= 100.0,
    },
    {
        "field_patterns": ["temperature", "temp"],
        "rule": "Temperature must be between -80 and 200",
        "check": lambda v: -80.0 <= float(v) <= 200.0,
    },
]


def _matches(field_name: str, patterns: List[str]) -> bool:
    fn = field_name.lower()
    return any(p in fn for p in patterns)


def validate_row(
    data: Dict[str, Any],
    schema_fields: List[Dict] = None,
) -> Tuple[bool, List[str]]:
    """
    Validate one data dict against scientific rules.
    Returns (is_valid, list_of_violation_messages).
    """
    violations = []

    # Schema-level validation (min/max from field definition)
    if schema_fields:
        for field_def in schema_fields:
            name = field_def.get("name", "")
            val = data.get(name)
            if val is None:
                continue
            validation = field_def.get("validation") or {}
            try:
                num = float(val)
                if "min" in validation and num < validation["min"]:
                    violations.append(f"{name}: {num} < min {validation['min']}")
                if "max" in validation and num > validation["max"]:
                    violations.append(f"{name}: {num} > max {validation['max']}")
            except (TypeError, ValueError):
                pass

    # Global scientific rules
    for rule in SCIENTIFIC_RULES:
        for field, val in data.items():
            if val is None:
                continue
            if _matches(field, rule["field_patterns"]):
                try:
                    if not rule["check"](val):
                        violations.append(f"{field}: {rule['rule']} (got {val})")
                except (TypeError, ValueError):
                    pass

    return len(violations) == 0, violations
