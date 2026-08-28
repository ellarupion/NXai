"""Адрес, с которого пришёл текущий запрос.

Через contextvar, а не параметром функции. Адрес — свойство соединения, а не решения
оператора: протаскивать его через record_audit из десятка роутеров значило бы ни разу
не забыть, а забыть — легко, и тогда часть записей журнала молча осталась бы без
адреса. Здесь его один раз кладёт middleware API, и любая запись журнала подхватывает
его сама.

Пусто (None) — нормальное состояние для всего, что происходит вне HTTP-запроса:
планировщик, воркер приёма постов, хендлеры ботов. У них нет ни адреса, ни человека,
и запись «система» честнее выдуманного адреса.
"""

from contextvars import ContextVar, Token

_actor_ip: ContextVar[str | None] = ContextVar("actor_ip", default=None)


def set_actor_ip(ip: str | None) -> Token:
    return _actor_ip.set(ip)


def reset_actor_ip(token: Token) -> None:
    _actor_ip.reset(token)


def current_actor_ip() -> str | None:
    return _actor_ip.get()
