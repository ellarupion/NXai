# Деплой (отдельный VPS)

Один VPS только под NXai, домен на Cloudflare (`ai.nxauto.org` или любой
другой — не хардкожен в конфиге, см. `deploy/nginx/nginx.conf`). Всё
собирается прямо на сервере (`docker compose ... up --build`) — локальная
сборка не нужна.

Если вместо этого NXai живёт рядом с другим проектом на общем nginx —
см. `git log -- DEPLOY.md docker-compose.prod.yml` на более раннюю версию
этого файла (сценарий "несколько проектов на одном VPS"), она никуда не
делась, просто это больше не текущий вариант.

## 0. Предпосылки

- Домен, указывающий A-записью на сервер (нужен для Let's Encrypt).
- Открыты порты 80 и 443.
- `.env` заполнен и **не закоммичен** — живёт только на диске сервера.

## 1. Клонирование и .env

```bash
cd /opt
git clone https://github.com/ellarupion/NXai.git nxai
cd nxai
cp .env.example .env
```

Дальше — **заполнить `.env` вручную через редактор** (`nano .env`), не
собирать его heredoc'ом/`read`-подсказками из чата: любая многострочная
вставка в терминал (особенно с мобильного SSH-клиента) рвётся на перенос
строк — `read` внутри такого куска перехватывает не то, что нужно, heredoc
может слипнуться в одну строку. Обычное редактирование файла построчно
никак не зависит от поведения терминала при вставке — самый надёжный способ
завести секреты, при всём желании обойтись без него.

Обязательно заполнить: `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`,
`TELEGRAM_API_ID`/`TELEGRAM_API_HASH` (my.telegram.org), `ADMIN_BOT_TOKEN`,
`API_SECRET_KEY` (`openssl rand -hex 32` — можно вставить командой, это не
секрет, вводимый руками, а генерируемый на месте).

## 2. Первый запуск (без TLS ещё нет — курица и яйцо)

Сертификат Let's Encrypt выпускается через HTTP-01 challenge, а challenge
должен раздавать уже работающий nginx на 80 порту — сначала поднимаем стек с
самоподписанным сертификатом-заглушкой, потом меняем на настоящий.

```bash
mkdir -p certs
openssl req -x509 -nodes -days 1 -newkey rsa:2048 -keyout certs/privkey.pem -out certs/fullchain.pem -subj "/CN=localhost"
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Проверьте, что миграция прошла и все контейнеры поднялись:

```bash
docker compose -f docker-compose.prod.yml ps
```

`migrate` должен быть `Exited (0)`, остальные — `Up`/`Up (healthy)`. Полная
схема (15 таблиц) создаётся одной командой без ручного вмешательства —
включая расширение `pgvector`, оно теперь бутстрапится прямо в миграции.

Заведите первого админа панели (пароль вводится интерактивно, не аргументом):

```bash
docker compose -f docker-compose.prod.yml exec api python scripts/create_admin.py --username admin --superadmin
```

Проверьте, что `/.well-known/acme-challenge/` действительно отдаётся наружу
(порт 80, без редиректа):

```bash
curl -I http://<домен>/.well-known/acme-challenge/ping
```

`404` — нормально, важно что не connection refused и не redirect.

## 3. Настоящий сертификат (certbot, webroot)

`docker-compose.prod.yml` содержит два вспомогательных сервиса за
`profile: tools` — не стартуют с обычным `up`, вызываются вручную. Certbot
кладёт challenge-файлы в тот же volume, что nginx отдаёт на 80 порту
(`certbot_webroot`), поэтому webroot-режим работает без остановки nginx:

```bash
docker compose -f docker-compose.prod.yml --profile tools run --rm certbot certonly --webroot -w /var/www/certbot -d <домен> --email <ваш-email> --agree-tos --non-interactive
docker compose -f docker-compose.prod.yml --profile tools run --rm -e DOMAIN=<домен> certs-sync
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

nginx.conf смонтирован как volume (не вшит в образ, в отличие от NX) —
`nginx -s reload` подхватывает и сертификат, и любые будущие правки конфига
без пересборки образа.

Проверка: `curl -I https://<домен>/api/health` → `{"status":"ok"}`.

## 4. Продление сертификата

Let's Encrypt сертификаты живут 90 дней. Добавьте на сервер cron:

```cron
0 3 * * 1 cd /opt/nxai && docker compose -f docker-compose.prod.yml --profile tools run --rm certbot renew --webroot -w /var/www/certbot && docker compose -f docker-compose.prod.yml --profile tools run --rm -e DOMAIN=<домен> certs-sync && docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

## 5. Про ботов — без вебхуков

`interfaces/bots/main.py` и `interfaces/telethon_workers/main.py` работают
через long polling/MTProto — им не нужен ни входящий порт, ни домен, только
исходящий доступ в интернет. Домен нужен только ради `api` (панели).

`ingest`/`bots` контейнеры будут в рестарт-петле, пока в базе нет ни одной
`TelethonSession`/`ChannelBot` — это ожидаемо для чистого разворачивания, не
баг. Наполнение (первая тема, Telethon-сессия, тематический бот) — отдельный
шаг после того, как сам стенд поднят, см. ROADMAP.md Phase 1.

## 6. Безопасность

- `postgres`/`redis` не публикуют порты наружу.
- `ufw allow 22,80,443/tcp; ufw enable`.
- `.env` только на диске сервера, не в git.
- `docker compose logs` не должны содержать секретов в открытом виде —
  `core/logging.py` их не логирует явно, но проверяйте при добавлении новых
  сервисов.
