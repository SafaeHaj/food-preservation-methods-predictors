from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    DATABASE_URL: str = "sqlite:///./food_research.db"

    # AI provider — pick ONE:
    #   vertexai  : Vertex AI (ADC + GCP project must have aiplatform.user IAM role)
    #   google_ai : Google AI Studio API key (free key from aistudio.google.com)
    #   openai    : OpenAI API key
    #   anthropic : Anthropic API key
    AI_PROVIDER: str = "vertexai"

    # --- Vertex AI (ADC / service account) ---
    VERTEX_PROJECT: str = "joinagent-8467d"
    VERTEX_LOCATION: str = "us-central1"
    VERTEX_MODEL: str = "gemini-2.5-flash"

    # --- Google AI Studio (free API key, no GCP IAM needed) ---
    GOOGLE_API_KEY: str = ""
    GOOGLE_AI_MODEL: str = "gemini-2.0-flash"

    # --- OpenAI ---
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # --- Anthropic ---
    ANTHROPIC_API_KEY: str = ""

    # --- Groq (free tier, no billing needed) ---
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "groq/compound"
    # llama-3.3-70b-versatile used directly for food extraction (12 000 TPM, JSON mode native).
    # groq/compound misroutes response_format requests to openai/gpt-oss-120b (8 000 TPM only).
    GROQ_FOOD_MODEL: str = "llama-3.3-70b-versatile"

    AI_MAX_TOKENS: int = 16384

    MAX_UPLOAD_SIZE_MB: int = 50
    MAX_PAPERS_PER_UPLOAD: int = 10
    UPLOAD_DIR: str = "uploads"

    # Docling / PP-Chart2Table cache directories (relative to backend root)
    DOCLING_CACHE_DIR: str = "uploads/docling_cache"
    CHART_CACHE_DIR: str = "uploads/chart_cache"
    # Bump DOCLING_CACHE_VERSION to invalidate all cached extractions
    DOCLING_CACHE_VERSION: str = "1"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_PATH = BASE_DIR / settings.UPLOAD_DIR
UPLOAD_PATH.mkdir(exist_ok=True)
