from collections import Counter, defaultdict
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import ExtractedRow, Paper, Project, User

router = APIRouter(prefix="/projects/{project_id}/analytics", tags=["analytics"])


@router.get("")
def get_analytics(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    papers = db.query(Paper).filter(Paper.project_id == project_id).all()
    rows = db.query(ExtractedRow).filter(ExtractedRow.project_id == project_id).all()

    # Status breakdown
    status_counts = Counter(r.status for r in rows)
    paper_status_counts = Counter(p.status for p in papers)

    # Per-paper row counts
    paper_row_counts = defaultdict(int)
    for r in rows:
        paper_row_counts[r.paper_id] += 1

    paper_summary = [
        {
            "paper_id": p.id,
            "name": p.original_name,
            "status": p.status,
            "page_count": p.page_count,
            "row_count": paper_row_counts[p.id],
        }
        for p in papers
    ]

    # Field coverage — how many rows have non-null values per field
    schema_fields = project.schema
    field_coverage = {}
    if rows and schema_fields:
        for field in schema_fields:
            fn = field["name"]
            filled = sum(1 for r in rows if r.data.get(fn) not in (None, "", "null"))
            field_coverage[fn] = {
                "label": field.get("label", fn),
                "filled": filled,
                "total": len(rows),
                "pct": round(filled / len(rows) * 100, 1) if rows else 0,
            }

    # Numeric distributions for key numeric fields
    distributions: Dict[str, Any] = {}
    numeric_fields = [f for f in schema_fields if f.get("type") == "number"]
    for field in numeric_fields[:6]:  # limit to 6 fields
        fn = field["name"]
        values = []
        for r in rows:
            v = r.data.get(fn)
            if v is not None:
                try:
                    values.append(float(v))
                except (TypeError, ValueError):
                    pass
        if values:
            distributions[fn] = {
                "label": field.get("label", fn),
                "count": len(values),
                "min": round(min(values), 3),
                "max": round(max(values), 3),
                "mean": round(sum(values) / len(values), 3),
                "values": [round(v, 3) for v in values[:200]],  # cap for chart
            }

    # Categorical frequency for select fields
    categoricals: Dict[str, Any] = {}
    select_fields = [f for f in schema_fields if f.get("type") == "select"]
    for field in select_fields[:4]:
        fn = field["name"]
        counts: Counter = Counter()
        for r in rows:
            v = r.data.get(fn)
            if v:
                counts[str(v)] += 1
        if counts:
            categoricals[fn] = {
                "label": field.get("label", fn),
                "data": [{"value": k, "count": v} for k, v in counts.most_common(10)],
            }

    return {
        "summary": {
            "total_papers": len(papers),
            "total_rows": len(rows),
            "approved": status_counts.get("approved", 0),
            "pending": status_counts.get("pending", 0),
            "rejected": status_counts.get("rejected", 0),
        },
        "paper_status": dict(paper_status_counts),
        "papers": paper_summary,
        "field_coverage": field_coverage,
        "distributions": distributions,
        "categoricals": categoricals,
    }
