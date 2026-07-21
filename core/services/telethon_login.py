"""Веб-логин Telethon-сессии по шагам (телефон → код → опционально 2FA-пароль) —
замена интерактивному scripts/generate_telethon_session.py, чтобы новый аккаунт
в пул читателей (core/models/telethon_session.py) заводился из панели, а не по
SSH с терминалом, который принимает input().

Технически это работает потому, что StringSession, экспортированный сразу
после connect()+send_code_request(), уже содержит установленный auth key на
нужном Telegram DC — процесс между двумя HTTP-запросами не переживает открытое
TCP-соединение, поэтому именно этот exported session string (плюс
phone_code_hash) переносится в СЛЕДУЮЩИЙ запрос как временное состояние,
позволяя восстановить тот же "недологиненный" клиент и продолжить sign_in().
Хранится в Redis с коротким TTL (не в БД — это одноразовый артефакт логина,
а не постоянный секрет пула) и всегда удаляется сразу после успеха или ошибки
клиента, чтобы не оставлять недологиненные сессии висеть до истечения TTL."""

import json
from dataclasses import asdict, dataclass
from uuid import uuid4

import redis.asyncio as redis
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from core.config import Settings, get_settings
from core.logging import get_logger

logger = get_logger(__name__)

LOGIN_ATTEMPT_TTL_SECONDS = 10 * 60
_REDIS_KEY_PREFIX = "telethon_login:"


class TelethonLoginError(Exception):
    """Текст уходит в HTTP-ответ панели как есть — никогда не пробрасывайте
    сюда сырое исключение telethon с внутренними деталями транспорта."""


class PasswordRequiredError(TelethonLoginError):
    def __init__(self) -> None:
        super().__init__("Требуется пароль двухфакторной аутентификации")


class AttemptNotFoundError(TelethonLoginError):
    def __init__(self) -> None:
        super().__init__("Сессия входа не найдена или истекла — начните заново")


@dataclass
class LoginResult:
    label: str
    session_string: str


@dataclass
class _AttemptState:
    phone_number: str
    label: str
    session_string: str
    phone_code_hash: str


def _redis_client(settings: Settings) -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


async def _save_state(attempt_id: str, state: _AttemptState, settings: Settings) -> None:
    r = _redis_client(settings)
    try:
        await r.set(f"{_REDIS_KEY_PREFIX}{attempt_id}", json.dumps(asdict(state)), ex=LOGIN_ATTEMPT_TTL_SECONDS)
    finally:
        await r.aclose()


async def _load_state(attempt_id: str, settings: Settings) -> _AttemptState:
    r = _redis_client(settings)
    try:
        raw = await r.get(f"{_REDIS_KEY_PREFIX}{attempt_id}")
    finally:
        await r.aclose()
    if raw is None:
        raise AttemptNotFoundError()
    return _AttemptState(**json.loads(raw))


async def _delete_state(attempt_id: str, settings: Settings) -> None:
    r = _redis_client(settings)
    try:
        await r.delete(f"{_REDIS_KEY_PREFIX}{attempt_id}")
    finally:
        await r.aclose()


def _client_for(session_string: str | None, settings: Settings) -> TelegramClient:
    session = StringSession(session_string) if session_string else StringSession()
    return TelegramClient(session, settings.telegram_api_id, settings.telegram_api_hash)


async def start_login(phone_number: str, label: str, settings: Settings | None = None) -> str:
    """Отправляет код входа на phone_number, возвращает attempt_id для submit_code()."""
    settings = settings or get_settings()
    client = _client_for(None, settings)
    try:
        await client.connect()
        sent = await client.send_code_request(phone_number)
    except Exception as exc:
        await client.disconnect()
        logger.warning("telethon_login.send_code_failed", error=str(exc))
        raise TelethonLoginError(f"Не удалось отправить код: {exc}") from exc

    attempt_id = str(uuid4())
    state = _AttemptState(
        phone_number=phone_number,
        label=label,
        session_string=client.session.save(),
        phone_code_hash=sent.phone_code_hash,
    )
    await client.disconnect()
    await _save_state(attempt_id, state, settings)
    logger.info("telethon_login.code_sent", attempt_id=attempt_id)
    return attempt_id


async def submit_code(attempt_id: str, code: str, settings: Settings | None = None) -> LoginResult:
    """Успех -> LoginResult с финальным session_string. Если у аккаунта включена
    2FA — бросает PasswordRequiredError, состояние сохраняется, дальше вызывать
    submit_password() с тем же attempt_id."""
    settings = settings or get_settings()
    state = await _load_state(attempt_id, settings)

    client = _client_for(state.session_string, settings)
    try:
        await client.connect()
        await client.sign_in(phone=state.phone_number, code=code, phone_code_hash=state.phone_code_hash)
    except SessionPasswordNeededError:
        state.session_string = client.session.save()
        await client.disconnect()
        await _save_state(attempt_id, state, settings)
        raise PasswordRequiredError() from None
    except Exception as exc:
        await client.disconnect()
        logger.warning("telethon_login.sign_in_failed", error=str(exc))
        raise TelethonLoginError(f"Не удалось подтвердить код: {exc}") from exc

    session_string = client.session.save()
    await client.disconnect()
    await _delete_state(attempt_id, settings)
    logger.info("telethon_login.completed", attempt_id=attempt_id)
    return LoginResult(label=state.label, session_string=session_string)


async def submit_password(attempt_id: str, password: str, settings: Settings | None = None) -> LoginResult:
    settings = settings or get_settings()
    state = await _load_state(attempt_id, settings)

    client = _client_for(state.session_string, settings)
    try:
        await client.connect()
        await client.sign_in(password=password)
    except Exception as exc:
        await client.disconnect()
        logger.warning("telethon_login.password_sign_in_failed", error=str(exc))
        raise TelethonLoginError(f"Неверный пароль: {exc}") from exc

    session_string = client.session.save()
    await client.disconnect()
    await _delete_state(attempt_id, settings)
    logger.info("telethon_login.completed_with_password", attempt_id=attempt_id)
    return LoginResult(label=state.label, session_string=session_string)
