"""Чтение конфигурации и защита прода от дефолтного секрета.

Тесты здесь герметичные намеренно. `Settings(_env_file=None)` отключает чтение файла
`.env`, но НЕ отключает чтение переменных окружения — а у любого, кто запускал систему
локально, `API_SECRET_KEY` и `ENVIRONMENT` в оболочке выставлены. Без очистки
`test_prod_requires_real_api_secret_key` падал ровно у тех, кто работает с проектом
руками, и падал обманчиво: сообщение «в проде принимается дефолтный ключ» отправляет
читать `core/config.py`, хотя виновата переменная в шелле.
"""

import pytest

from core.config import Settings

# Всё, что pydantic-settings может подхватить из окружения и подменить значения,
# которые проверяют тесты ниже.
ENV_KEYS = (
    "ENVIRONMENT",
    "API_SECRET_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "ANTHROPIC_API_KEY",
    "VOYAGE_API_KEY",
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "LOG_LEVEL",
    "SENTRY_DSN",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_dev_settings_load_with_defaults():
    settings = Settings(_env_file=None)
    assert settings.environment == "dev"
    assert settings.is_prod is False


def test_prod_requires_real_api_secret_key():
    """Прод с дефолтным ключом подписи не должен подниматься вовсе: с ним любой, кто
    видел исходники, выпишет себе токен администратора панели."""
    with pytest.raises(ValueError):
        Settings(_env_file=None, environment="prod")


def test_prod_accepts_real_api_secret_key():
    settings = Settings(_env_file=None, environment="prod", api_secret_key="a" * 32)
    assert settings.is_prod is True


def test_env_var_still_reaches_settings(monkeypatch):
    """Сторож самой герметичности. Фикстура выше чистит окружение — но если однажды
    перестанет, соседний тест начнёт падать загадочно. Здесь переменная выставляется
    явно, и видно, что механизм чтения окружения работает: значит падение соседа
    означало бы именно поломку фикстуры, а не поведения Settings."""
    monkeypatch.setenv("API_SECRET_KEY", "b" * 32)
    settings = Settings(_env_file=None, environment="prod")
    assert settings.is_prod is True
