"""Кросспостинг рерайта в другие сети (аудит, п.8.4). Тот же текст, что ушёл
в Telegram, дублируется в VK и/или MAX, если это включено у целевого канала
(TargetChannel.crosspost). Best-effort: сбой кросспоста НЕ влияет на основную
Telegram-публикацию — вызывающая сторона логирует и идёт дальше.

Адаптеры реализуют общий интерфейс post(text) через реальные HTTP-API. Токены
доступа хранятся в конфиге канала и вводятся оператором в панели.

ВНИМАНИЕ: реальную доставку в VK/MAX можно проверить только с живыми токенами
и сетью — здесь тестируется логика выбора/формирования запроса на моках."""

from typing import Protocol

import httpx

from core.logging import get_logger

logger = get_logger(__name__)

VK_API_VERSION = "5.199"
VK_WALL_POST_URL = "https://api.vk.com/method/wall.post"
# MAX (max.ru) — Bot API, метод отправки сообщения в чат/канал.
MAX_SEND_URL = "https://botapi.max.ru/messages"

HTTP_TIMEOUT = 15.0


class CrossPostAdapter(Protocol):
    platform: str

    async def post(self, text: str) -> None: ...


class VKAdapter:
    platform = "vk"

    def __init__(self, access_token: str, owner_id: str) -> None:
        self._access_token = access_token
        # owner_id со знаком минус для сообществ (как требует VK API).
        self._owner_id = owner_id

    async def post(self, text: str) -> None:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(
                VK_WALL_POST_URL,
                data={
                    "owner_id": self._owner_id,
                    "from_group": 1,
                    "message": text,
                    "access_token": self._access_token,
                    "v": VK_API_VERSION,
                },
            )
        body = response.json()
        if "error" in body:
            raise RuntimeError(f"VK API error: {body['error'].get('error_msg', body['error'])}")


class MaxAdapter:
    platform = "max"

    def __init__(self, access_token: str, chat_id: str) -> None:
        self._access_token = access_token
        self._chat_id = chat_id

    async def post(self, text: str) -> None:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(
                MAX_SEND_URL,
                params={"access_token": self._access_token, "chat_id": self._chat_id},
                json={"text": text},
            )
        if response.status_code >= 400:
            raise RuntimeError(f"MAX API error {response.status_code}: {response.text[:200]}")


def build_adapters(crosspost_config: dict) -> list[CrossPostAdapter]:
    """Строит адаптеры только для включённых и полностью настроенных платформ."""
    adapters: list[CrossPostAdapter] = []
    vk = crosspost_config.get("vk") or {}
    if vk.get("enabled") and vk.get("access_token") and vk.get("owner_id"):
        adapters.append(VKAdapter(vk["access_token"], str(vk["owner_id"])))
    mx = crosspost_config.get("max") or {}
    if mx.get("enabled") and mx.get("access_token") and mx.get("chat_id"):
        adapters.append(MaxAdapter(mx["access_token"], str(mx["chat_id"])))
    return adapters


async def crosspost_text(crosspost_config: dict, text: str) -> int:
    """Публикует text во все включённые платформы канала. Возвращает число
    успешных доставок; ошибки логируются, но не пробрасываются (best-effort)."""
    delivered = 0
    for adapter in build_adapters(crosspost_config):
        try:
            await adapter.post(text)
            delivered += 1
            logger.info("crosspost.delivered", platform=adapter.platform)
        except Exception:
            logger.exception("crosspost.failed", platform=adapter.platform)
    return delivered
