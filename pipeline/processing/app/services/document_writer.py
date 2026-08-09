"""Persist a paper's bibliography and its prose.

Split from `science_writer` because it writes a different thing for a different reason:
the scientific tables are the extraction's output, while these are the document it was
read out of. A `prose` evidence span cites a section by `docling_item_ref`, so without
these rows the citation resolves to nothing.

Performs no commits. The caller wraps it in `unit_of_work` with the rest of the paper.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from shared.db.models import Paper, Section
from shared.schemas.science import GoldBundle


def write(db: Session, paper: Paper, bundle: GoldBundle) -> int:
    """Update the paper's bibliography and replace its sections. Returns sections written.

    Bibliographic fields are only filled where the bundle has something: re-extracting a
    paper whose title an operator corrected must not overwrite it with the file name the
    assembler fell back to.
    """
    document = bundle.paper
    if document.title and not paper.title:
        paper.title = document.title
    for field_name in ("doi", "abstract", "published_year"):
        value = getattr(document, field_name)
        if value is not None:
            setattr(paper, field_name, value)

    # Replaced rather than merged: sections are derived wholly from the parse, so a
    # re-extraction that found fewer of them should not leave the old ones behind.
    db.query(Section).filter(Section.paper_id == paper.id).delete(synchronize_session=False)
    for order, section in enumerate(bundle.sections):
        db.add(Section(
            paper_id=paper.id,
            section_order=order,
            section_title=section.section_title,
            content_markdown=section.content_markdown,
            page_number=section.page_number,
            docling_item_ref=section.docling_item_ref,
        ))
    db.flush()
    return len(bundle.sections)
