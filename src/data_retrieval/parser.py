"""
Stage 2: Convert PDFs to clean Markdown using Docling.

Entry point: run_parsing(pdf_dir, output_dir) -> list[Path]
"""

from __future__ import annotations

from pathlib import Path


def pdf_to_markdown(pdf_path: Path, output_dir: Path) -> Path:
    """
    Convert a single PDF to Markdown via Docling.

    Docling's layout model handles multi-column PDFs and preserves tables
    as Markdown tables automatically.
    """
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    md_text = result.document.export_to_markdown()

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / (pdf_path.stem + ".md")
    out_path.write_text(md_text, encoding="utf-8")
    return out_path


def run_parsing(pdf_dir: Path, output_dir: Path) -> list[Path]:
    """
    Batch-convert all PDFs in pdf_dir to Markdown.

    Skips files that already have a matching .md in output_dir.
    Returns list of .md file paths (newly converted + pre-existing).
    """
    pdf_paths = list(pdf_dir.glob("*.pdf"))
    if not pdf_paths:
        print(f"[parser] No PDFs found in {pdf_dir}")
        return []

    print(f"[parser] Parsing {len(pdf_paths)} PDFs ...")
    output_dir.mkdir(parents=True, exist_ok=True)
    md_paths: list[Path] = []

    for pdf_path in pdf_paths:
        out_path = output_dir / (pdf_path.stem + ".md")
        if out_path.exists():
            print(f"  [parser] Already parsed: {pdf_path.name}")
            md_paths.append(out_path)
            continue
        try:
            print(f"  [parser] Converting: {pdf_path.name}")
            md_path = pdf_to_markdown(pdf_path, output_dir)
            md_paths.append(md_path)
        except Exception as exc:
            print(f"  [parser] Failed {pdf_path.name}: {exc}")

    print(f"[parser] {len(md_paths)} Markdown files in {output_dir}")
    return md_paths
