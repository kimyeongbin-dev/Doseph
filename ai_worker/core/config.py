"""AI Worker configuration module.

This module contains configuration settings for the AI worker service
using modern Python configuration patterns with pydantic-settings.
"""

from dataclasses import field
import zoneinfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
  """AI Worker configuration class.

  This class handles configuration settings for the AI worker,
  including Redis connection, logging, and external API settings.
  Uses modern pydantic-settings for environment variable management.
  """

  model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")

  # Timezone settings
  TIMEZONE: zoneinfo.ZoneInfo = field(default_factory=lambda: zoneinfo.ZoneInfo("Asia/Seoul"))

  # Redis settings
  REDIS_URL: str = "redis://redis:6379/0"

  # Logging settings
  LOG_LEVEL: str = "INFO"

  # External API settings
  OPENAI_API_KEY: str | None = None

  # CLOVA OCR settings — 환경변수 이름과 정확히 일치 (.env 와 호환)
  CLOVA_OCR_INVOKE_URL: str | None = None
  CLOVA_OCR_SECRET_KEY: str | None = None

  # Public data API settings
  DATA_GO_KR_API_KEY: str | None = None


# Global configuration instance
config = Config()
