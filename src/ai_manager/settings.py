# src/utils/settings.py  (add these fields to your existing Settings class)
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    # Chat model
    LLM_MODEL: str
    LLM_PROVIDER: str = "ollama"
    LLM_BASE_URL: str
    LLM_STREAMING: bool = True
    AI_LOGIN_MOBILE: int | None = None
    AI_LOGIN_PASSWORD: str | None = None
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
    LANGSMITH_PROJECT: str

    # Search
    PRODUCT_SEARCH_SIZE: int = 50
    PRODUCT_SEARCH_RESULTS_TO_LLM: int = 10


settings = Settings()