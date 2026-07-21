from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Единая точка чтения конфигурации для core, telethon-воркеров, ботов и api.

    В отличие от NX здесь нет фиксированного BOT_TOKEN на процесс: число
    тематических ботов растёт из панели (см. core/models/channel_bot.py),
    поэтому токены живут в БД (ChannelBot.bot_token, шифруются как secret),
    а не в .env. Здесь остаются только вещи, общие для всего процесса —
    БД/redis/LLM-ключи/Telethon-креды/секрет панели."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["dev", "prod"] = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://nxai:nxai@localhost:5432/nxai"
    redis_url: str = "redis://localhost:6379/0"

    anthropic_api_key: str = ""
    voyage_api_key: str = ""

    # Telethon API-креды для ВСЕГО пула ingest-сессий (api_id/api_hash одинаковы для
    # всех аккаунтов одного приложения на my.telegram.org). Сами session string'и —
    # по одному на TelethonSession (core/models/telethon_session.py), не здесь: их
    # список растёт вместе с числом source_channels и не влезает в статичный .env.
    telegram_api_id: int = 0
    telegram_api_hash: str = ""

    sentry_dsn: str = ""

    api_secret_key: str = "dev-secret-change-me"
    telegram_login_bot_username: str = ""

    admin_bot_token: str = ""

    # Ключ шифрования секретов в БД (bot_token, session_string) — валидный
    # Fernet-ключ (`python -c "from cryptography.fernet import Fernet;
    # print(Fernet.generate_key().decode())"`). Если пуст, ключ детерминированно
    # выводится из api_secret_key — работает без доп. настройки, но привязывает
    # расшифровку к тому же секрету, что и JWT; в проде задавайте отдельный.
    secrets_encryption_key: str = ""

    @model_validator(mode="after")
    def _prod_requires_real_api_secret(self) -> "Settings":
        if self.environment == "prod" and self.api_secret_key in ("", "dev-secret-change-me"):
            raise ValueError(
                "API_SECRET_KEY обязателен в проде (ENVIRONMENT=prod): "
                "сгенерируйте `openssl rand -hex 32` и задайте в .env"
            )
        return self

    @property
    def is_prod(self) -> bool:
        return self.environment == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
