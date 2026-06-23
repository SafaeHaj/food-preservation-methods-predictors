"""Upload an Excel file to infer schema fields from its columns."""
import json
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import Project, User
from app.schemas.projects import SchemaField

router = APIRouter(prefix="/schema", tags=["schema"])


@router.post("/infer", response_model=List[SchemaField])
async def infer_schema_from_excel(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """
    Upload an Excel file; returns a list of SchemaField definitions inferred
    from column names and data types.
    """
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only .xlsx or .xls files are accepted")

    try:
        import pandas as pd
        from io import BytesIO

        content = await file.read()
        df = pd.read_excel(BytesIO(content), nrows=50)
    except Exception as e:
        raise HTTPException(400, f"Could not read Excel: {e}")

    fields: List[SchemaField] = []
    for col in df.columns:
        col_str = str(col)
        col_lower = col_str.lower().replace(" ", "_")

        # Infer type
        dtype = df[col].dtype
        if dtype in ("int64", "float64"):
            field_type = "number"
            validation = {}
            if any(k in col_lower for k in ("ph",)):
                validation = {"min": 0, "max": 14}
            elif any(k in col_lower for k in ("cfu", "count", "log")):
                validation = {"min": 0, "max": 12}
            elif any(k in col_lower for k in ("percent", "pct", "humidity")):
                validation = {"min": 0, "max": 100}
            elif any(k in col_lower for k in ("conc", "concentration")):
                validation = {"min": 0}
        elif dtype == "bool":
            field_type = "boolean"
            validation = None
        else:
            unique_vals = df[col].dropna().unique().tolist()
            if 2 <= len(unique_vals) <= 8 and all(isinstance(v, str) for v in unique_vals):
                field_type = "select"
            else:
                field_type = "text"
            validation = None

        # Infer unit hint from column name
        unit = ""
        if "g/100g" in col_str or "g_per_100g" in col_lower:
            unit = "g/100g"
        elif "mg/l" in col_lower or "mg/ml" in col_lower:
            unit = "mg/L"
        elif "log_cfu" in col_lower or "log cfu" in col_lower:
            unit = "log CFU/g"
        elif col_lower.endswith("_c") or "temp" in col_lower:
            unit = "°C"
        elif "day" in col_lower:
            unit = "days"

        label = col_str.replace("_", " ").title()

        field = SchemaField(
            name=col_lower,
            label=label,
            type=field_type,
            unit=unit or None,
            required=False,
            validation=validation if validation else None,
        )
        if field_type == "select":
            field.options = [str(v) for v in df[col].dropna().unique().tolist()[:10]]

        fields.append(field)

    return fields
