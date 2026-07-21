# NXai

Мультиканальный агрегатор Telegram-контента по темам: Telethon-воркеры читают
чужие тематические каналы-источники, ранжируют посты по вирусности
(пересылки), сводят дубли, делают LLM-рерайт под персону канала и
автоматически публикуют через отдельного бота на каждую тему — с шафлом
порядка и джиттером времени, чтобы не повторять источник. Отдельный
админ-бот собирает уведомления и статистику со всех тематических ботов.

Архитектура и план работ: см. [`ARCHITECTURE.md`](./ARCHITECTURE.md) и
[`ROADMAP.md`](./ROADMAP.md). Деплой на отдельный VPS (свой nginx+certbot,
Cloudflare) — [`DEPLOY.md`](./DEPLOY.md).

Проект — идейный родственник [NX](https://github.com/ellarupion/NX)
(панель редакции черновиков), часть инфраструктурного кода (`core/config`,
`core/db`, `core/llm`, `core/embeddings`, статистика, паттерны сервисов)
переиспользована и адаптирована оттуда.

## Статус

Phase 0 — скелет проекта: ядро (config/db/llm/embeddings), полная схема
данных, docker-compose, JWT-авторизация панели, заготовки сервисов и
интерфейсов. Миграция и весь путь `docker compose up` → `alembic upgrade
head` → создание админа → `/health`/`/auth/login` проверены end-to-end на
реальном Postgres+pgvector. Бизнес-логика ingestion/scoring/rewrite/
scheduling реализована на урезанном объёме (см. `core/services/`) — полная
оркестрация нескольких Telethon-сессий и React-панель ещё предстоят, см.
`ROADMAP.md`.

## Стек

Python 3.12, Telethon (MTProto-чтение чужих каналов), aiogram 3 (боты
на публикацию), FastAPI + SQLAlchemy(async) + asyncpg + alembic + pgvector,
APScheduler, Redis (шина событий), litellm (LLM-рерайт поверх Anthropic).

## Быстрый старт (после наполнения Phase 1)

```bash
cp .env.example .env   # заполнить токены/ключи
docker compose up --build
```
