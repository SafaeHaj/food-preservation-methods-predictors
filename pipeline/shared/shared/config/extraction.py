"""Extraction-service settings: uploads, Docling, chart conversion, the schema gate.

Extraction reads documents. It has no LLM settings and no vocabulary path any more -- both
moved to `ProcessingSettings` with the code that uses them, so a provider or a term is
configured on the service that calls it rather than on the one that happens to have parsed
the PDF.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.base import storage_subpath


class ExtractionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_prefix="EXTRACTION_",
    )

    # ── Uploads ───────────────────────────────────────────────────────────────
    MAX_UPLOAD_SIZE_MB: int = 50
    MAX_PAPERS_PER_UPLOAD: int = 10

    # ── Docling ───────────────────────────────────────────────────────────────
    #: Relative by default, resolved against the storage root (STORAGE_DIR) -- NOT against
    #: BASE_DIR. These caches belong inside the uploads volume the API and worker share;
    #: resolving them against BASE_DIR put them at /uploads in the container's own
    #: filesystem, because `shared` installs at /shared where BASE_DIR computes to "/".
    #: Nothing failed visibly: the containers ran as root, so the stray directory was
    #: created happily, unshared and discarded on every recreate.
    DOCLING_CACHE_DIR: str = "docling_cache"
    CHART_CACHE_DIR: str = "chart_cache"
    #: Bump to invalidate every cached extraction after a pipeline change. At "3": text
    #: items gained heading structure and reading order, and the parse now carries its own
    #: page images. An older cache loads without error and is silently missing both.
    DOCLING_CACHE_VERSION: str = "3"

    #: Docling's table-structure model. `accurate` reads merged headers better and costs
    #: several times as long per page.
    TABLE_STRUCTURE: bool = True
    TABLE_STRUCTURE_MODE: str = "fast"   # fast | accurate

    #: OCR is decided per paper, not once for the deployment: a born-digital PDF already
    #: carries its text, and running an OCR model over every bitmap region of every one of
    #: its pages buys nothing. A paper is "native" when its first NATIVE_TEXT_SAMPLE_PAGES
    #: pages already yield this many characters.
    NATIVE_TEXT_THRESHOLD: int = 150
    NATIVE_TEXT_SAMPLE_PAGES: int = 2
    #: Resolution figures and page previews are exported at, relative to the page. Below
    #: ~1.5 a chart's tick labels stop being legible to the converter. This replaced a
    #: separate PyMuPDF render scale: Docling already rasterises every page, so a second
    #: library rendering them again at its own zoom was work and a dependency for nothing.
    IMAGES_SCALE: float = 1.5

    # ── The schema gate ───────────────────────────────────────────────────────
    #: Off, every figure that passes the geometry probe is admitted without its chart being
    #: read. That changes what the data means, not only how long extraction takes, so it is
    #: recorded in the job result rather than being a silent switch.
    REQUIRE_FIGURE_DATA: bool = True
    #: Three opt-in figure filters. All reject real charts along with photographs; the gate
    #: report says what share each would have rejected, which is what to read before
    #: enabling any of them.
    FIGURE_EDGE_FILTER: bool = False
    FIGURE_CAPTION_FILTER: bool = False
    #: Stricter than FIGURE_CAPTION_FILTER, and judged on the caption alone rather than on
    #: the caption plus its surrounding prose: admit only figures whose own caption names a
    #: plotted quantity, so chart conversion -- by far the most expensive step per figure --
    #: is spent on the measurement series and not on every diagram in the paper.
    FIGURE_REQUIRE_PLOT_CAPTION: bool = False
    #: How much surrounding prose a figure carries into interpretation.
    FIGURE_CONTEXT_CHARS: int = 1200
    #: How many figures the chart converter is given at once, and how large each may be.
    #: The batch is halved and retried on an out-of-memory error, so this is a ceiling.
    CHART_BATCH_SIZE: int = 8
    CHART_MAX_PIXELS: int = 1024
    #: Chart-to-table is long-output autoregressive generation. Without a bound, one figure
    #: the model cannot read decodes until it stops itself, which on CPU is minutes; a real
    #: chart's table is a few hundred tokens, so this cuts only the runaway case.
    CHART_MAX_NEW_TOKENS: int = 1024
    #: Rows of an unresolved asset kept in its preview. Processing shows that preview to a
    #: model when it asks which column is the axis, but the preview is rendered here, when
    #: the package is built.
    REVIEW_PREVIEW_ROWS: int = 10

    # ── Evidence auto-selection ───────────────────────────────────────────────
    # Which assets are sent to the LLM when the user has not curated the selection by hand.
    # Previously hardcoded as _AUTO_SCORE / _AUTO_TABLE_SCORE / _NON_SCI inside a
    # background function, where they were untunable and invisible.
    AUTO_SELECT_MIN_SCORE: float = 3.0
    AUTO_SELECT_MIN_TABLE_SCORE: float = 1.0
    NON_SCIENTIFIC_CLASSIFICATIONS: list[str] = [
        "publisher_logo",
        "license_icon",
        "decorative_asset",
    ]

    # ── Paging ────────────────────────────────────────────────────────────────
    DEFAULT_ASSET_PAGE_SIZE: int = 100
    MAX_ASSET_PAGE_SIZE: int = 500

    #: Read buffer for hashing and line-counting generated CSVs.
    FILE_CHUNK_BYTES: int = 65536

    @property
    def docling_cache_path(self) -> Path:
        return storage_subpath(self.DOCLING_CACHE_DIR)

    @property
    def chart_cache_path(self) -> Path:
        return storage_subpath(self.CHART_CACHE_DIR)

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@lru_cache
def get_extraction_settings() -> ExtractionSettings:
    return ExtractionSettings()
