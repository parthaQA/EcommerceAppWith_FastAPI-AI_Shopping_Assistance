# src/ai_manager/settings.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"   # project root, same file as app settings


class AISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        extra="ignore",               # .env also holds DB_CONNECTION, REDIS_URL, etc.
    )

    # Chat model
    LLM_MODEL: str
    LLM_PROVIDER: str = "ollama"
    LLM_BASE_URL: str
    LLM_STREAMING: bool = True

    # Guardrails
    GROQ_API_KEY: str
    GUARDRAIL_MODEL: str
    GUARDRAIL_TEMPERATURE: float = 0
    GUARDRAIL_REQUESTS_PER_SECOND: float = 0.25
    GUARDRAIL_CHECK_INTERVAL: float = 0.05
    GUARDRAIL_BUCKET_SIZE: int = 1

    # Agent runtime
    AGENT_RECURSION_LIMIT: int = 25
    AGENT_TAGS: list[str] = ["shopping"]

    # Tracing
    LANGSMITH_PROJECT: str = "ecom-agent"

    # What the LLM sees
    PRODUCT_SEARCH_RESULTS_TO_LLM: int = 10


ai_settings = AISettings()