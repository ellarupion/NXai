# Архитектура NXai

## 1. Отличие от NX

NX: авторы сами пишут готовые посты в приватный «черновик»-канал → бот
читает его через Bot API `channel_post` → редактор публикует вручную.
Источник — свой, доверенный, бот в нём администратор.

NXai: источники — чужие публичные каналы по темам. Бот не админ в них →
Bot API не отдаёт ни `channel_post`-апдейты чужого канала, ни
`views`/`forwards`. Поэтому входная часть системы — не webhook, а
**Telethon-юзербот**, слушающий чужие каналы как обычный подписчик.
Публикующая часть (боты на каналы, статистика, панель) устроена почти
как в NX и переиспользуется.

NX — outbox с одобрением. NXai — inbox-агрегатор с автопаблишем.

⚠️ Рерайт чужого контента и постоянный мониторинг чужих каналов
юзер-аккаунтом — серая зона (авторское право, ToS Telegram на
автоматизацию user-сессий). Технические меры снижения риска — см. §7,
но выбор источников и итоговая ответственность — за оператором системы.

## 2. Компоненты

```
Telethon Ingest Pool (N сессий, шардинг по каналам)
        │  events.NewMessage → candidate_posts (status=NEW)
        ▼
Scoring service (переопрос views/forwards в Telethon: +30м/+2ч/+6ч,
                 score = forwards / channel_median_forwards_7d)
        ▼
Dedup (pgvector, embedding cosine, HIGH=0.92 — сворачивает репосты
       одной новости из разных source_channels в одного representative)
        ▼
Rewrite (LLM, per-theme style/persona prompt, запрет копировать
         структуру/порядок исходного текста)
        ▼
Pool + Scheduler (шафл: взвешенно-случайный выбор по score, не FIFO;
                  джиттер времени; каданс/тихие часы per bot)
        ▼
Channel Bots (N, свой tg bot_token на тему/канал) ──▶ Target Channels
        │
        │  Bot API channel_post: свой канал, но пост не от нашего бота
        ▼
Ad Watchdog (ad_detections → таймер 60 мин → форс-паблиш лучшего
             READY-поста из pool_posts темы поверх рекламы)
        ▼
Admin Bot (агрегирует все события всех тематических ботов + дайджесты)

Admin Panel (FastAPI + React, как в NX): темы ↔ боты ↔ source_channels,
пул кандидатов, ad-watchdog лог, статистика.
```

## 3. Процессы (контейнеры)

| Сервис | Роль |
|---|---|
| `postgres` (pgvector) | данные + эмбеддинги; дедуп **включён** в пайплайн (в NX был построен, но не подключён) |
| `redis` | шина событий ingest → scoring → dedup → rewrite, `core/events.py` |
| `ingest` | пул Telethon-сессий, живой приём кандидатов (`interfaces/telethon_workers`) |
| `bots` | один процесс, N Dispatcher'ов — по одному на tg-токен темы + admin-бот (`interfaces/bots`) |
| `api` | админ-панель (`interfaces/api`), структура роутеров как в NX |
| `scheduler` | APScheduler, все периодические джобы одним процессом (`scheduler.py`): переопрос метрик кандидатов, дедуп+рерайт, паблиш из пула с шафлом, ad-watchdog тик |
| `web` / `nginx` | Vite+React-панель (вход, темы, источники) + reverse-proxy |

Scoring/dedup/rewrite сознательно не вынесены в отдельные сервисы в Phase 0/1
(живут как job'ы `scheduler.py`, см. §5) — это самый простой вариант деплоя;
разделение на независимо масштабируемые процессы имеет смысл только когда
объём кандидатов реально упрётся в производительность одного APScheduler-тика
(см. ROADMAP.md Phase 5).

## 4. Модель данных

- **`themes`** — тема/ниша (`men`, `women`, …): `name`, `default_style_prompt`, `target_channel_id`.
- **`channel_bots`** — токен бота на тему: `theme_id`, `bot_token` (хранится как secret-override, не в git), `persona_prompt`, `cadence` (мин/макс интервал, постов/день, тихие часы), `is_active`, `role` (`THEME` / `ADMIN` — admin-бот через ту же таблицу с ролью).
- **`source_channels`** — чужой канал-источник: `tg_username`/`tg_chat_id`, `theme_id` (назначается в панели), `ingest_session_id`, `last_scanned_message_id` (watermark докачки), `is_active`, `trust_score`.
- **`candidate_posts`** — ядро пайплайна: `source_channel_id`, `tg_message_id` (уникальны вместе — идемпотентность как в NX `drafts`), `raw_text`, `first_seen_at`, `embedding (vector(1024))`, `duplicate_of_id` (self-FK), `status` (`NEW → SCORING → SELECTED → REWRITTEN → QUEUED → PUBLISHED / REJECTED / DUPLICATE`), `theme_id`.
- **`metrics_snapshots`** — временной ряд `views/forwards/reactions` по `candidate_post_id`, несколько точек во времени (пост «дозревает» 2-6 часов).
- **`post_versions`** — рерайт-версии кандидата (как в NX `post_versions`), плюс `source_similarity` (расстояние от оригинала — анти-плагиат метрика).
- **`pool_posts`** — собственный запасной пул (evergreen-контент на тему), используется и для обычного заполнения расписания, и для перекрытия рекламы.
- **`publications`** — факт публикации в целевой канал + метрики (как в NX).
- **`ad_detections`** — чужой пост в *своём* целевом канале: `target_channel_id`, `tg_message_id`, `detected_at`, `covering_publication_id`, `action` (`auto_buried`/`ignored`).
- **`target_channels`, `admins`, `audit_logs`, `panel_settings`** — перенесены из NX почти без изменений.

Подробности полей — см. docstring-и в `core/models/*.py`.

## 5. Ключевые алгоритмы

**Скоринг.** Сырые `forwards` нечестно сравнивать между каналом на 5к и на
500к подписчиков: `score = forwards / channel_median_forwards_7d`
(альтернатива — z-score), плюс скорость набора в первый час как сигнал
вирусности. Три контрольные точки дозревания: +30 мин / +2 ч / +6 ч,
финальный отбор — по последнему доступному снапшоту.

**Кросс-канальный дедуп.** В NX было реализовано, но не подключено к
пайплайну — здесь это критично, т.к. вирусный пост расползается по
десяткам каналов одной тематики одновременно. embedding + pgvector
cosine distance, порог `HIGH_SIMILARITY_THRESHOLD = 0.92`. Внутри группы
дублей выбирается representative с максимальным score, остальные →
`DUPLICATE`.

**Рерайт.** System-prompt на тему явно запрещает LLM сохранять исходный
порядок абзацев/зачин, просит переставить порядок фактов, сменить длину,
добавить хук/CTA под персону канала. Диф-дистанция от оригинала (как
word-diff в NX `draft_generation.py`) логируется как контроль качества.

**Шафл порядка выхода.** Пул READY-постов на тему — не FIFO. Планировщик
выбирает пост взвешенно-случайно (score как вес) в рамках каданса бота
(N постов/день, мин. интервал, тихие часы), джиттер времени публикации
± X минут — чтобы порядок/тайминг выхода не совпадал с источником.

**Авто-перекрытие рекламы.** Детект чужого поста в целевом канале
(webhook, бот там админ — тот же механизм, что `core/services/foreign_post.py`
в NX, но без шага ручного подтверждения) → таймер 60 мин → если на этот
слот ещё не запланирован свой пост, форс-паблиш лучшего READY-поста из
`pool_posts` темы поверх → уведомление в admin-бот с тем, что перекрыли.

## 6. Что переиспользовано из NX

Почти без изменений: `core/config.py`, `core/db.py`, `core/logging.py`,
`core/events.py`, `core/llm/client.py` (litellm + Anthropic + prompt
caching — меняются только промпты), `core/embeddings/client.py`,
`core/services/dedup.py` (включается в пайплайн), формулы engagement из
`core/statistics`/`core/services/analytics.py`, auth/JWT в
`interfaces/api`, конвенции `web/` (стек, `api/client.ts`-паттерн, дизайн-
токены Tailwind v4), `docker-compose*.yml`, `deploy/nginx`, alembic-сетап,
`scripts/generate_telethon_session.py`, `scripts/create_admin.py`.

Основа для Ad Watchdog — `core/services/foreign_post.py` +
`interfaces/bot/handlers/foreign_post.py` из NX, с удалением шага
ручного подтверждения.

Написано с нуля: Telethon ingest-воркеры с шардингом каналов по сессиям,
scoring service, multi-bot runner (динамическое число токенов вместо
двух фиксированных в NX), shuffle-scheduler, автоматический (без
подтверждения) ad watchdog.

## 7. Технические ограничения и риски

- **Flood-лимиты Telegram**: одна user-сессия надёжно держит ограниченное
  число каналов и не должна делать частые `GetHistoryRequest`; каналы
  шардируются по нескольким сессиям (`ingest_session_id` в
  `source_channels`), новые сессии добавляются по мере роста списка
  источников, а не путём «раздувания» одной.
- **Стоимость эмбеддингов/LLM** растёт с числом source-каналов линейно —
  дедуп на этапе эмбеддинга должен идти до дорогого шага рерайта, а не
  после.
- **Задержка дозревания метрик** (2-6 часов на скоринг) — фичи как
  «утренний дайджест» в NX здесь становятся частью логики отбора, а не
  просто отчётностью.
- **Секреты по каналам**: `bot_token` в `channel_bots` — не в `.env`
  (число тем растёт динамически из панели), хранить как
  `panel_settings`-style secret-override с шифрованием в БД, никогда не
  в git/логах.
