"""Export approved data to a multi-sheet Excel workbook."""
import json
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List

import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


def _style_header(ws):
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")


def _autofit(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                max_len = max(max_len, len(str(cell.value or "")))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 4, 50)


def build_excel(
    project_name: str,
    schema_fields: List[Dict],
    papers: List[Dict],
    rows: List[Dict],
) -> bytes:
    """
    Build a multi-sheet Excel file in memory and return bytes.

    Sheets:
    1. Project_Summary
    2. All_Approved_Data
    3. By_Paper (one sheet per paper, max 20)
    4. Provenance
    5. Validation_Report
    6. Schema_Dictionary
    """
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # 1. Project Summary
        summary_data = {
            "Item": ["Project", "Export Date", "Total Papers", "Total Rows", "Approved", "Pending", "Rejected"],
            "Value": [
                project_name,
                datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                len(papers),
                len(rows),
                sum(1 for r in rows if r["status"] == "approved"),
                sum(1 for r in rows if r["status"] == "pending"),
                sum(1 for r in rows if r["status"] == "rejected"),
            ],
        }
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name="Project_Summary", index=False)
        _style_header(writer.sheets["Project_Summary"])
        _autofit(writer.sheets["Project_Summary"])

        # 2. All Approved Data
        field_names = [f["name"] for f in schema_fields]
        approved_rows = [r for r in rows if r["status"] == "approved"]

        if approved_rows:
            records = []
            for r in approved_rows:
                paper_name = next((p["original_name"] for p in papers if p["id"] == r["paper_id"]), "")
                rec = {"row_id": r["id"], "paper": paper_name, "status": r["status"]}
                data = r.get("data", {})
                for fn in field_names:
                    rec[fn] = data.get(fn)
                records.append(rec)
            df_all = pd.DataFrame(records)
            df_all.to_excel(writer, sheet_name="All_Approved_Data", index=False)
            _style_header(writer.sheets["All_Approved_Data"])
            _autofit(writer.sheets["All_Approved_Data"])
        else:
            pd.DataFrame({"note": ["No approved rows yet"]}).to_excel(
                writer, sheet_name="All_Approved_Data", index=False
            )

        # 3. Per-Paper sheets (up to 20)
        paper_map = {p["id"]: p for p in papers}
        for i, paper in enumerate(papers[:20]):
            paper_rows = [r for r in approved_rows if r["paper_id"] == paper["id"]]
            if not paper_rows:
                continue
            sheet_name = f"Paper_{i+1}"[:31]
            records = []
            for r in paper_rows:
                rec = {"row_id": r["id"]}
                data = r.get("data", {})
                for fn in field_names:
                    rec[fn] = data.get(fn)
                records.append(rec)
            df_paper = pd.DataFrame(records)
            df_paper.to_excel(writer, sheet_name=sheet_name, index=False)
            _style_header(writer.sheets[sheet_name])
            _autofit(writer.sheets[sheet_name])

        # 4. Provenance
        prov_records = []
        for r in rows:
            paper_name = next((p["original_name"] for p in papers if p["id"] == r["paper_id"]), "")
            prov = r.get("provenance", {})
            for field, info in prov.items():
                if isinstance(info, dict):
                    prov_records.append({
                        "row_id": r["id"],
                        "paper": paper_name,
                        "field": field,
                        "page": info.get("page"),
                        "table": info.get("table"),
                        "confidence": info.get("confidence"),
                    })
        df_prov = pd.DataFrame(prov_records) if prov_records else pd.DataFrame(
            {"note": ["No provenance data"]}
        )
        df_prov.to_excel(writer, sheet_name="Provenance", index=False)
        _style_header(writer.sheets["Provenance"])
        _autofit(writer.sheets["Provenance"])

        # 5. Validation Report
        val_records = [
            {
                "row_id": r["id"],
                "paper": next((p["original_name"] for p in papers if p["id"] == r["paper_id"]), ""),
                "status": r["status"],
                "reviewer_note": r.get("reviewer_note", ""),
            }
            for r in rows
            if r.get("reviewer_note")
        ]
        df_val = pd.DataFrame(val_records) if val_records else pd.DataFrame(
            {"note": ["No validation notes"]}
        )
        df_val.to_excel(writer, sheet_name="Validation_Report", index=False)
        _style_header(writer.sheets["Validation_Report"])
        _autofit(writer.sheets["Validation_Report"])

        # 6. Schema Dictionary
        dict_records = []
        for f in schema_fields:
            val = f.get("validation") or {}
            dict_records.append({
                "field_name": f["name"],
                "label": f.get("label", ""),
                "type": f.get("type", ""),
                "unit": f.get("unit", ""),
                "required": f.get("required", False),
                "min": val.get("min", ""),
                "max": val.get("max", ""),
                "options": ", ".join(f.get("options") or []),
            })
        df_dict = pd.DataFrame(dict_records) if dict_records else pd.DataFrame({"note": ["No schema"]})
        df_dict.to_excel(writer, sheet_name="Schema_Dictionary", index=False)
        _style_header(writer.sheets["Schema_Dictionary"])
        _autofit(writer.sheets["Schema_Dictionary"])

    return output.getvalue()
