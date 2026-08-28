#!/usr/bin/env bash
#
# Локальный стек одной командой: Postgres, Redis, миграции, API и панель.
#
# Зачем. Песочница и чистая машина каждый раз требуют одного и того же набора действий,
# и половина из них неочевидна: pgvector ставится отдельным пакетом, ENVIRONMENT принимает
# только 'dev' или 'prod', TELEGRAM_API_ID пустой строкой не проходит валидацию. Каждый
# раз выяснять это заново — потерянные полчаса.
#
#   scripts/dev_stack.sh up      поднять всё
#   scripts/dev_stack.sh status  что живо
#   scripts/dev_stack.sh down    погасить API и панель (база остаётся)
#
# База НЕ гасится и не чистится: в ней накапливаются данные, по которым удобно проверять
# панель, и терять их при каждом перезапуске незачем.

set -euo pipefail
cd "$(dirname "$0")/.."

ROOT="$(pwd)"
VENV="${VENV:-$ROOT/.venv}"
ENV_FILE="${ENV_FILE:-$ROOT/.env.dev}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"
RUN_DIR="${RUN_DIR:-/tmp/nxai-dev}"

log()  { printf '\033[36m▸\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*"; }

write_env_file() {
    [ -f "$ENV_FILE" ] && return
    log "создаю $ENV_FILE"
    # Ключ шифрования секретов — 32 байта в base64. Значение фиксированное и заведомо
    # не секретное: это локальная машина, а разный ключ между запусками сделал бы
    # нечитаемыми уже сохранённые токены ботов.
    cat > "$ENV_FILE" <<'EOF'
DATABASE_URL=postgresql+asyncpg://nxai:nxai@localhost:5432/nxai
REDIS_URL=redis://localhost:6379/0
API_SECRET_KEY=dev-secret-key-not-for-prod
SECRET_ENCRYPTION_KEY=ZGV2LWtleS1mb3ItbG9jYWwtdGVzdGluZy0zMmJ5dGVzIQ==
ANTHROPIC_API_KEY=
VOYAGE_API_KEY=
TELEGRAM_API_ID=12345
TELEGRAM_API_HASH=dev-hash
ENVIRONMENT=dev
EOF
}

start_db() {
    if ! pg_isready -q 2>/dev/null; then
        log "поднимаю Postgres"
        service postgresql start >/dev/null 2>&1 || sudo service postgresql start >/dev/null 2>&1
        sleep 2
    fi
    pg_isready -q || { warn "Postgres не поднялся"; exit 1; }

    if ! sudo -u postgres psql -tAc "select 1 from pg_roles where rolname='nxai'" 2>/dev/null | grep -q 1; then
        log "завожу пользователя и базу nxai"
        sudo -u postgres psql -q -c "CREATE USER nxai WITH PASSWORD 'nxai' SUPERUSER;" || true
        sudo -u postgres psql -q -c "CREATE DATABASE nxai OWNER nxai;" || true
    fi
    # Расширение ставится отдельным пакетом: без него падают миграции на CREATE EXTENSION,
    # и ошибка выглядит как проблема с миграцией, а не с окружением.
    if ! sudo -u postgres psql -d nxai -q -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null; then
        warn "нет pgvector — ставлю пакет"
        sudo apt-get install -y -q postgresql-16-pgvector >/dev/null
        sudo -u postgres psql -d nxai -q -c "CREATE EXTENSION IF NOT EXISTS vector;"
    fi
    ok "Postgres и база nxai"

    if ! redis-cli ping >/dev/null 2>&1; then
        log "поднимаю Redis"
        redis-server --daemonize yes >/dev/null 2>&1
        sleep 1
    fi
    redis-cli ping >/dev/null 2>&1 && ok "Redis" || warn "Redis не поднялся"
}

up() {
    mkdir -p "$RUN_DIR"
    write_env_file
    start_db

    [ -d "$VENV" ] || { warn "нет виртуального окружения в $VENV — см. CLAUDE.md, раздел «Окружение»"; exit 1; }

    set -a; . "$ENV_FILE"; set +a
    export PYTHONPATH="$ROOT"

    log "миграции"
    "$VENV/bin/python" -m alembic upgrade head >/dev/null
    ok "схема на последней версии"

    log "админ dev/dev12345"
    "$VENV/bin/python" - <<'EOF' >/dev/null 2>&1 || true
import asyncio
from core.db import get_session_factory
from core.services.admin import AdminService

async def main():
    async with get_session_factory()() as s:
        await AdminService(s).create_admin("dev", "dev12345", True)
        await s.commit()

asyncio.run(main())
EOF
    ok "админ dev / dev12345"

    if ! curl -sf "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then
        log "API на :$API_PORT"
        nohup "$VENV/bin/python" -m uvicorn interfaces.api.main:app \
            --host 127.0.0.1 --port "$API_PORT" --log-level warning \
            > "$RUN_DIR/api.log" 2>&1 &
        echo $! > "$RUN_DIR/api.pid"
        sleep 4
    fi
    ok "API :$API_PORT"

    if ! curl -sf "http://127.0.0.1:$WEB_PORT/" >/dev/null 2>&1; then
        log "панель на :$WEB_PORT"
        ( cd web && nohup npm run dev -- --port "$WEB_PORT" > "$RUN_DIR/web.log" 2>&1 & echo $! > "$RUN_DIR/web.pid" )
        sleep 4
    fi
    ok "панель http://localhost:$WEB_PORT  (вход dev / dev12345)"
}

status() {
    pg_isready -q 2>/dev/null && ok "Postgres" || warn "Postgres лежит"
    redis-cli ping >/dev/null 2>&1 && ok "Redis" || warn "Redis лежит"
    curl -sf "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 \
        && ok "API :$API_PORT" || warn "API :$API_PORT не отвечает"
    curl -sf "http://127.0.0.1:$WEB_PORT/" >/dev/null 2>&1 \
        && ok "панель :$WEB_PORT" || warn "панель :$WEB_PORT не отвечает"
}

down() {
    for name in api web; do
        if [ -f "$RUN_DIR/$name.pid" ]; then
            kill "$(cat "$RUN_DIR/$name.pid")" 2>/dev/null || true
            rm -f "$RUN_DIR/$name.pid"
            ok "$name погашен"
        fi
    done
    log "база и Redis оставлены — данные для проверок в них накапливаются"
}

case "${1:-}" in
    up)     up ;;
    status) status ;;
    down)   down ;;
    *)      echo "использование: $0 {up|status|down}" >&2; exit 1 ;;
esac
