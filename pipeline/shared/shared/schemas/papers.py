from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PaperOut(BaseModel):
    """A paper as the workspace sees it.

    `row_count` (legacy flat extracted rows) was replaced by the two counts that describe
    the current pipeline: how much Docling found, and how much the LLM turned into
    structured experiments.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    filename: str
    original_name: str
    page_count: int
    status: str
    error_message: str
    uploaded_at: datetime
    asset_count: int = 0
    experiment_count: int = 0
