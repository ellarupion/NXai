# Деплой: несколько проектов на одном VPS + Cloudflare

Сценарий: один VPS (Kamatera), домен `nxauto.org` на Cloudflare, на нём уже
живёт NX на `i.nxauto.org`, и рядом нужно поднять NXai на `ai.nxauto.org`.
Всё собирается прямо на сервере (`docker compose ... up --build`) — локальная
сборка не нужна ни для NX (там она и так под Docker), ни для NXai.

Ключевая идея: порты 80/443 на хосте может держать только один процесс.
Раз у NX уже есть свой `nginx`-контейнер с TLS — он и остаётся единственным
входом на VPS, а NXai подключается к нему через общую docker-сеть, не
поднимая свой nginx и не публикуя `api` наружу напрямую.

## 1. Один раз на VPS: общая сеть

```bash
docker network create edge
```

Эта сеть — единственная точка соприкосновения проектов. NXai подключает к
ней `api` (см. `docker-compose.prod.yml` — уже настроено в этом репозитории).
Со стороны NX нужно один раз добавить ту же сеть существующему `nginx`-сервису
в его `docker-compose.prod.yml` (репозиторий NX здесь не трогаем — правьте
прямо на сервере или в своём чекауте NX):

```yaml
services:
  nginx:
    # ...остальное как было...
    networks:
      - default
      - edge

networks:
  default:
  edge:
    external: true
```

После правки: `docker compose -f docker-compose.prod.yml up -d nginx`
(пересоздаст только nginx, остальные сервисы NX не тронет).

## 2. Cloudflare: DNS

DNS → Add record:
- Type: `A`
- Name: `ai`
- Content: `<IP вашего VPS>` (тот же, что у `i.nxauto.org`)
- Proxy status: Proxied (оранжевое облако) — прячет IP VPS, DDoS-защита.

## 3. Cloudflare: TLS — Origin Certificate (рекомендуется)

Сейчас у NX, судя по всему, TLS через certbot/Let's Encrypt (HTTP-01,
см. его DEPLOY.md) — рабочий вариант, но требует cron-обновления сертификата
раз в ~60 дней. Раз домен уже на Cloudflare, проще один раз выпустить
**Cloudflare Origin Certificate** (валиден 15 лет, Cloudflare доверяет ему
по умолчанию) и полностью убрать certbot:

1. Cloudflare → SSL/TLS → Origin Server → Create Certificate.
2. Hostnames: `nxauto.org, *.nxauto.org` (покрывает и `i`, и `ai`, и будущие
   поддомены), Key type RSA, срок 15 лет.
3. Сохранить на VPS: `/etc/ssl/cloudflare/origin.pem` (сертификат) и
   `/etc/ssl/cloudflare/origin.key` (приватный ключ), смонтировать
   read-only в контейнер nginx (тот же volume-путь, что сейчас у
   fullchain.pem/privkey.pem в NX — просто заменить содержимое).
4. Cloudflare → SSL/TLS → Overview → режим **Full (strict)**.

После этого certbot/certs-sync в NX можно не запускать вовсе — Origin Cert
не обновляется годами и не требует HTTP-01 challenge.

Если не хочется трогать уже работающий certbot-конфиг NX — второй вариант:
выпустить обычный Let's Encrypt сертификат ещё и на `ai.nxauto.org` тем же
certbot-контейнером (`certbot certonly --webroot -w /var/www/certbot -d
ai.nxauto.org`) и подключить его в новом server-блоке ниже. Дольше в
поддержке, зато без изменения текущей TLS-схемы.

## 4. Разворачивание NXai на VPS

```bash
cd /opt
git clone https://github.com/ellarupion/NXai.git nxai
cd nxai
cp .env.example .env
nano .env   # заполнить прямо на сервере: токены ботов, ANTHROPIC_API_KEY,
            # VOYAGE_API_KEY, TELEGRAM_API_ID/HASH, API_SECRET_KEY (openssl rand -hex 32)
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
docker compose -f docker-compose.prod.yml exec api python scripts/create_admin.py --username admin
```

`--build` собирает образ прямо на сервере из `Dockerfile` — ничего собирать
локально не нужно.

## 5. Подключить к общему nginx

В `nginx.conf` NX (на сервере) добавить ещё один server-блок — рядом с
существующим для `i.nxauto.org`:

```nginx
server {
    listen 80;
    server_name ai.nxauto.org;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }  # если остаётся certbot
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl;
    server_name ai.nxauto.org;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;   # или cf-origin.pem, см. §3
    ssl_certificate_key /etc/nginx/certs/privkey.pem;      # или cf-origin.key

    add_header Strict-Transport-Security "max-age=63072000" always;

    location /api/ {
        proxy_pass http://nxai-api:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Пока нет собранного web/ для NXai (ROADMAP.md Phase 1+) — заглушка.
    location / {
        return 404;
    }
}
```

`http://nxai-api:8000` резолвится по имени контейнера (`container_name:
nxai-api` уже задан в `docker-compose.prod.yml`), потому что NX-нginx и
NXai-api сидят в одной сети `edge` — не нужен ни host-порт, ни IP.

Применить: `docker compose -f docker-compose.prod.yml exec nginx nginx -s reload`
(или пересоздать контейнер, если правили volume с конфигом).

Проверка: `curl -I https://ai.nxauto.org/api/health` → `{"status":"ok"}`.

## 6. Про ботов — без вебхуков и доменов

`interfaces/bots/main.py` и `interfaces/telethon_workers/main.py` работают
через long polling/MTProto — им не нужен ни входящий порт, ни домен, только
исходящий доступ в интернет. Поэтому `ai.nxauto.org` в этой схеме нужен
только ради `api` (панели) — рост числа тематических ботов никак не меняет
сетевую конфигурацию.

## 7. Безопасность

- `postgres`/`redis` не публикуют порты наружу ни в NX, ни здесь (см.
  `docker-compose.prod.yml`) — доступны только внутри своих docker-сетей.
- `ufw allow 22,80,443/tcp; ufw enable` — весь остальной трафик на VPS не нужен
  снаружи вообще (даже 8000 у NXai теперь закрыт, см. §4/`api.networks`).
- `.env` только на сервере, не в git (см. `.gitignore`).
