"""Extraction-service settings: uploads, Docling, chart conversion, LLM ingestion.

Fields here replace values that were previously literals inside route and service modules
(relevance thresholds, the page-render zoom, the Groq base URL, CSV read chunk sizes), so
tuning the pipeline no longer means editing source.
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
    #: Bump to invalidate every cached extraction after a pipeline change.
    DOCLING_CACHE_VERSION: str = "1"

    #: PyMuPDF render scale for page previews. 1.5 ≈ 108 DPI: legible in the workspace
    #: without producing multi-megabyte PNGs for every page of every paper.
    PAGE_RENDER_ZOOM: float = 1.5

    # ── LLM ─────────────────────────────────────────────────────────────────────
    # The ingestion LLM speaks the OpenAI chat API. Two providers sit behind one client:
    #   * ollama (default) — a local server in the `ollama` container, no API key, so the
    #     stack extracts out of the box. Ollama exposes an OpenAI-compatible /v1 endpoint,
    #     so the same client and the same JSON-mode prompt drive it unchanged.
    #   * groq — Groq's hosted Llama, used when LLM_PROVIDER=groq and a key is set.
    LLM_PROVIDER: str = "ollama"   # ollama | groq

    # Ollama (local, default). A reduced Llama 3 (llama3.2:3b) runs on CPU in the ollama
    # container; raise OLLAMA_MODEL to e.g. llama3.1:8b for better extraction accuracy where
    # the host can afford it. Must match the tag pulled by the `ollama-pull` compose service.
    OLLAMA_BASE_URL: str = "http://ollama:11434/v1"
    OLLAMA_MODEL: str = "llama3.2:3b"
    #: A local model on CPU is slower than a hosted one; give one package call room to finish.
    LLM_TIMEOUT_SECONDS: float = 300.0

    # Groq (hosted). Only consulted when LLM_PROVIDER=groq.
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    #: llama-3.3-70b-versatile is used directly: 12 000 TPM and native JSON mode.
    #: groq/compound misroutes response_format requests to a model with 8 000 TPM.
    GROQ_FOOD_MODEL: str = "llama-3.3-70b-versatile"

    LLM_ENABLE_VERIFICATION: bool = True

    @property
    def llm_base_url(self) -> str:
        return self.OLLAMA_BASE_URL if self.LLM_PROVIDER == "ollama" else self.GROQ_BASE_URL

    @property
    def llm_model(self) -> str:
        return self.OLLAMA_MODEL if self.LLM_PROVIDER == "ollama" else self.GROQ_FOOD_MODEL

    @property
    def llm_api_key(self) -> str:
        # Ollama ignores the key, but the OpenAI SDK refuses to init without a non-empty one.
        return "ollama" if self.LLM_PROVIDER == "ollama" else self.GROQ_API_KEY

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
