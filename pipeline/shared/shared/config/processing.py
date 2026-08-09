"""Processing-service settings: the LLM seam, the vocabulary, external APIs, datasets.

Processing owns everything with food-science meaning. Extraction reads documents and stops;
the model provider, the controlled vocabulary and the external enrichment keys are all
configured here, on the service that actually calls them.

Every field is `PROCESSING_`-prefixed. The LLM block moved wholesale from
`ExtractionSettings`, so an existing deployment renames `EXTRACTION_LLM_*` to
`PROCESSING_LLM_*` -- there is no compatibility shim, because a silently-ignored provider
key is worse than a startup failure that names the variable.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.base import BASE_DIR, storage_subpath

#: `processing/config/`, holding the files the service ships rather than generates -- the
#: controlled vocabulary. `BASE_DIR` is the deployment root (the repository in a checkout,
#: `/` in the container, where the service lives at /app).
SERVICE_CONFIG_DIR = next(
    (candidate for candidate in (
        BASE_DIR / "processing" / "config",
        Path("/app/config"),
        Path.cwd() / "config",
    ) if candidate.is_dir()),
    BASE_DIR / "processing" / "config",
)


class ProcessingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_prefix="PROCESSING_",
    )

    # ── LLM ───────────────────────────────────────────────────────────────────
    # Everything provider-independent lives here; which provider these apply to is
    # `LLM_PROVIDER`, and what each provider defaults to is one table in
    # `app.services.llm.registry`. Switching to a paid API is this field plus its key.
    #
    # An empty LLM_MODEL or LLM_BASE_URL means "the provider's default", so changing
    # provider alone is a valid, complete change.
    LLM_PROVIDER: str = "ollama"   # ollama | openai | anthropic | groq | gemini | fake
    LLM_MODEL: str = ""
    LLM_BASE_URL: str = ""

    #: 0.0 throughout: the model reads two prose fields out of a methods section, and a
    #: sampled answer to that question is a different answer, not a better one.
    LLM_TEMPERATURE: float = 0.0
    #: 0 = the provider's own default. Sizing this below a reasoning model's natural trace
    #: length ends the call before any JSON is emitted.
    LLM_MAX_OUTPUT_TOKENS: int = 0
    #: A local model on CPU is slower than a hosted one; give one call room to finish.
    LLM_TIMEOUT_SECONDS: float = 600.0
    LLM_RETRIES: int = 3
    LLM_RETRY_BACKOFF: float = 2.0

    #: Constrain decoding with a JSON Schema where the provider supports it. Off by default:
    #: on some Ollama builds the grammar is applied to the reasoning channel too, which
    #: mangles the answer. `LLMClient.probe()` reports whether this deployment is safe.
    LLM_JSON_SCHEMA: bool = False
    #: true | false | low | medium | high. Drives Ollama's `think`, OpenAI's
    #: `reasoning_effort` and Gemini's thinking budget; providers with no reasoning channel
    #: ignore it.
    LLM_REASONING: str = "true"

    #: Replies are cached on the prompts themselves, so editing a prompt or changing model
    #: invalidates exactly the answers it could have changed. A re-queued paper pays once.
    LLM_CACHE_ENABLED: bool = True
    LLM_CACHE_DIR: str = "llm_cache"

    #: Ceiling on one prompt. The effective budget is the lower of this and what the
    #: provider's context window affords, so a wider model widens the prompt by itself.
    LLM_MAX_PROMPT_CHARS: int = 24000

    # Keys. Env only, no defaults, never logged. A provider selected without its key fails
    # at client construction naming the variable -- not mid-run, and not with the value.
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    # Ollama server hints. No other provider has an equivalent, so they are namespaced
    # rather than pretending to be general: `keep_alive` and `num_ctx` are meaningless to a
    # hosted API, whose context window is fixed per model.
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"
    OLLAMA_NUM_CTX: int = 16384
    OLLAMA_NUM_PREDICT: int = 0
    OLLAMA_KEEP_ALIVE: str = "-1"

    # ── The vocabulary and normalisation ──────────────────────────────────────
    #: Where the controlled vocabulary lives. Empty resolves to the file shipped in the
    #: service's own `config/`; set it to bind-mount a project-specific vocabulary without
    #: rebuilding the image.
    VOCABULARY_PATH: str = ""
    #: How far into a section normalisation scans for the paper's matrix.
    SECTION_SCAN_CHARS: int = 2000
    #: How much of the prose around an asset the Gold prompt carries as its context.
    FIGURE_CONTEXT_CHARS: int = 1200
    #: Rows of an unresolved asset shown to the review call, which only names its axis.
    REVIEW_PREVIEW_ROWS: int = 10
    #: Treatment and application-method classification asks the Gold call to arbitrate when
    #: the keyword pass matches nothing or matches two things. Off, both fall to their sink
    #: values and the no-model path stays viable.
    CLASSIFY_WITH_LLM: bool = True

    # ── Dataset ───────────────────────────────────────────────────────────────
    #: On the shared uploads volume: relative, resolved by `storage_subpath` against
    #: STORAGE_DIR so the API and the Celery worker see the same files.
    DATASET_DIR: str = "datasets"
    MODEL_ARTIFACT_DIR: str = "model_artifacts"

    # ── Prediction service (training and inference are delegated) ─────────────
    PREDICTION_SERVICE_URL: str = "http://prediction:8100"
    #: A Weibull-AFT fit with an R-frailty second stage can legitimately run for minutes.
    PREDICTION_TIMEOUT_SECONDS: float = 600.0

    #: Engine names the prediction service exposes. Kept here rather than as literals at the
    #: call site: they were previously duplicated into the training task, where they had to
    #: be held in lockstep with the prediction service by hand, and any drift left a
    #: placeholder row stuck in "pending" forever.
    SURVIVAL_ENGINES: list[str] = ["weibull_aft", "rsf", "gbs"]

    @property
    def llm_cache_path(self) -> Path:
        return storage_subpath(self.LLM_CACHE_DIR)

    @property
    def vocabulary_file(self) -> Path:
        """The configured vocabulary, or the one shipped with the service."""
        if self.VOCABULARY_PATH:
            return Path(self.VOCABULARY_PATH)
        return SERVICE_CONFIG_DIR / "vocabulary.yaml"

    @property
    def dataset_path(self) -> Path:
        return storage_subpath(self.DATASET_DIR)

    @property
    def model_artifact_path(self) -> Path:
        return storage_subpath(self.MODEL_ARTIFACT_DIR)


@lru_cache
def get_processing_settings() -> ProcessingSettings:
    return ProcessingSettings()
