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
интерфейсов, минимальная веб-панель (`web/` — вход, темы, источники).
Весь путь `docker compose up` → `alembic upgrade head` → создание админа →
логин в браузере → создание темы → назначение темы источнику проверен
end-to-end (реальный Postgres+pgvector + реальный собранный фронтенд в
headless-браузере). Бизнес-логика ingestion/scoring/rewrite/scheduling
реализована на урезанном объёме (см. `core/services/`) — полная оркестрация
нескольких Telethon-сессий, пул кандидатов и статистика в панели ещё
предстоят, см. `ROADMAP.md`.

## Стек

Backend: Python 3.12, Telethon (MTProto-чтение чужих каналов), aiogram 3
(боты на публикацию), FastAPI + SQLAlchemy(async) + asyncpg + alembic +
pgvector, APScheduler, Redis (шина событий), litellm (LLM-рерайт поверх
Anthropic).

Frontend (`web/`): Vite + React 19 + TypeScript + react-router +
@tanstack/react-query + Tailwind v4 — тот же стек, что у `web/` в NX.

## Быстрый старт

```bash
cp .env.example .env   # заполнить токены/ключи
docker compose up --build

cp web/.env.example web/.env
cd web && npm install && npm run dev   # панель на localhost:5173, проксирует /api на :8000
```
