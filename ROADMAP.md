# Roadmap

## Phase 0 — Skeleton (этот коммит)

- Документация (`ARCHITECTURE.md`, этот файл).
- Ядро: `core/config.py`, `core/db.py`, `core/logging.py`, `core/events.py`.
- `core/llm/client.py`, `core/embeddings/client.py` — адаптированы из NX.
- Полная схема данных в `core/models/*` (см. `ARCHITECTURE.md` §4).
- Заготовки сервисов (`core/services/*`) и интерфейсов
  (`interfaces/telethon_workers`, `interfaces/bots`, `interfaces/api`) с
  рабочими сигнатурами и TODO там, где нужна бизнес-логика.
- `docker-compose.yml`, `Dockerfile`, `alembic.ini`, `.env.example`.

Не реализовано: реальный ingest/scoring/dedup-wiring/rewrite/scheduler —
это Phase 1+.

## Phase 1 — MVP одной темы, без автопаблиша

- [ ] `interfaces/telethon_workers`: одна сессия, 3-5 source-каналов
      одной темы, `events.NewMessage` → запись `candidate_posts`.
- [ ] `core/services/scoring.py`: скоринг по последнему доступному
      снапшоту (без трёх контрольных точек — упрощённая версия).
- [ ] `core/services/dedup.py`: подключить к пайплайну (в NX было
      реализовано, но не вызывалось).
- [ ] `core/services/rewrite.py`: LLM-рерайт с одним style-prompt.
- [ ] Публикация — **вручную** через `interfaces/api` (панель), чтобы
      проверить качество рерайта и дедупа на реальных данных перед тем,
      как включать автопаблиш.
- [ ] Первая alembic-миграция (`alembic revision --autogenerate`).

## Phase 2 — Автопаблиш + шафл

- [ ] `core/services/scheduler_pool.py`: взвешенно-случайный выбор +
      джиттер, каданс/тихие часы на бота.
- [ ] `scheduler.py`: job публикации из пула (аналог
      `run_due_publications_job` в NX, но источник — `pool_posts`/
      `candidate_posts`, а не ручной клик).
- [ ] Admin-бот: базовые уведомления (новая публикация, ошибка).

## Phase 3 — Мультитематика

- [ ] `themes` + `channel_bots`: N тем, N токенов, multi-bot runner в
      `interfaces/bots/main.py` (один процесс — Dispatcher на токен).
- [ ] Шардинг Telethon-сессий по темам/нагрузке
      (`source_channels.ingest_session_id`).
- [ ] Панель: страница назначения `source_channel → theme`.

## Phase 4 — Ad Watchdog + собственный пул

- [ ] Детект чужого поста в целевом канале (портировать логику
      `foreign_post.py` из NX, убрать шаг подтверждения).
- [ ] `pool_posts`: наполнение (вручную из панели и/или проактивная
      LLM-генерация evergreen-контента).
- [ ] Авто-перекрытие через 60 минут + уведомление в admin-бот.

## Phase 5 — Полная статистика

- [ ] Дашборды по темам/ботам/источникам (продуктивность источника —
      сколько его постов реально дошло до публикации; переиспользовать
      `engagement_rate` из NX).
- [ ] Алерты (просадка по теме, застой пула, source без выхлопа N дней).
- [ ] Возможный вывод неэффективных source_channels из ротации по
      `trust_score`.
