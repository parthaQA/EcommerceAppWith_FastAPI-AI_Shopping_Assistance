from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DB_CONNECTION: str = Field(
        validation_alias=AliasChoices("DB_CONNECTION", "DATABASE_URL")
    )
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    EXP_TIME: int
    ACCESS_TOKEN_EXP_MINUTES: int | None = None
    REFRESH_TOKEN_EXP_DAYS: int = 7
    REDIS_URL: str | None = None
    RABBITMQ_URL: str = "amqp://guest:guest@localhost/"
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:5173,"
        "http://127.0.0.1:3000,http://127.0.0.1:5173"
    )
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    CSV_MAX_BYTES: int = 1_048_576
    CSV_MAX_ROWS: int = 500
    PRODUCT_LIST_MAX_LIMIT: int = 100
    AI_LOGIN_MOBILE: int | None = None
    AI_LOGIN_PASSWORD: str | None = None
    MIN_PASSWORD_LENGTH: int = 8
    ORDER_AUTO_ACCEPT_MINUTES: int = 5

    @property
    def access_token_minutes(self) -> int:
        if self.ACCESS_TOKEN_EXP_MINUTES is not None:
            return self.ACCESS_TOKEN_EXP_MINUTES
        return self.EXP_TIME

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

settings = Settings()