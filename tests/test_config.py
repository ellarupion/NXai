from core.config import Settings


def test_dev_settings_load_with_defaults():
    settings = Settings(_env_file=None)
    assert settings.environment == "dev"
    assert settings.is_prod is False


def test_prod_requires_real_api_secret_key():
    try:
        Settings(_env_file=None, environment="prod")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for default api_secret_key in prod")


def test_prod_accepts_real_api_secret_key():
    settings = Settings(_env_file=None, environment="prod", api_secret_key="a" * 32)
    assert settings.is_prod is True
