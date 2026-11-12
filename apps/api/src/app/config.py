from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process settings, read from the environment (prefix ``ATTESTRWA_``)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    cors_origins: str = Field(default="", validation_alias="ATTESTRWA_CORS_ORIGINS")
    api_version: str = Field(default="2.0.0", validation_alias="ATTESTRWA_API_VERSION")
    log_level: str = Field(default="INFO", validation_alias="ATTESTRWA_LOG_LEVEL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
