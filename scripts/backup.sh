#!/usr/bin/env bash
#
# Резервная копия базы NXai.
#
# Зачем. Бэкапов в проекте не было вовсе — а в базе лежит то, что не восстановить
# ниоткуда: накопленная статистика источников и их надёжность (trust_score строится
# неделями наблюдений), векторы дедупликации, история версий постов, персоны ботов и
# зашифрованные сессии аккаунтов-читалок. Потеря сессий отдельно неприятна: их придётся
# заводить заново кодом из Telegram на каждый аккаунт.
#
# Дамп — не бэкап, пока его не восстановили хотя бы раз. Поэтому два режима:
#
#   scripts/backup.sh                 снять дамп, проверить целостность, убрать старые
#   scripts/backup.sh --restore-check восстановить последний дамп в отдельную базу и
#                                     показать, сколько строк доехало
#
# Настройки — переменными окружения:
#
#   BACKUP_DIR   куда класть дампы                       (по умолчанию /var/backups/nxai)
#   KEEP_DAYS    сколько дней хранить                    (по умолчанию 14)
#   OFFSITE_CMD  команда для копии вне сервера, получает  (по умолчанию пусто)
#                путь к файлу единственным аргументом,
#                например: OFFSITE_CMD="rclone copy --to backup:nxai"
#
# Копия на том же сервере спасает от ошибки («снёс не ту таблицу») и не спасает от
# потери сервера. Пока OFFSITE_CMD пуст, бэкап неполный, и скрипт об этом говорит.

set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-/var/backups/nxai}"
KEEP_DAYS="${KEEP_DAYS:-14}"
OFFSITE_CMD="${OFFSITE_CMD:-}"

# Переопределяется переменной окружения — чтобы скрипт можно было прогнать не только на
# прод-стеке (например, проверить на локальной базе, подставив свою обёртку).
DC="${DC:-docker compose -f docker-compose.prod.yml}"
DB_USER="${DB_USER:-nxai}"
DB_NAME="${DB_NAME:-nxai}"

log() { printf '%s  %s\n' "$(date +'%F %T')" "$*"; }
die() { log "ОШИБКА: $*"; exit 1; }

restore_check() {
    local latest scratch
    latest="$(ls -1t "$BACKUP_DIR"/nxai-*.sql.gz 2>/dev/null | head -1)" || true
    [ -n "${latest:-}" ] || die "в $BACKUP_DIR нет ни одного дампа"
    scratch="restore_check_$(date +%s)"

    log "проверка восстановлением: $latest → база $scratch"
    $DC exec -T postgres createdb -U "$DB_USER" "$scratch"
    # Что бы ни случилось дальше — временную базу за собой убираем: проверка,
    # оборвавшаяся на полпути, оставила бы мусор, который однажды займёт диск.
    # Кавычки двойные намеренно: имя базы подставляется сейчас, а не в момент выхода.
    trap "$DC exec -T postgres dropdb -U $DB_USER --if-exists $scratch >/dev/null 2>&1 || true" EXIT

    # ON_ERROR_STOP=1 — иначе psql проглотит ошибки и отчитается об успехе на битом
    # дампе, то есть ровно в том случае, ради которого проверка и делается.
    gunzip -c "$latest" | $DC exec -T postgres \
        psql -v ON_ERROR_STOP=1 -q -U "$DB_USER" -d "$scratch" >/dev/null

    log "восстановилось, строки в основных таблицах:"
    $DC exec -T postgres psql -U "$DB_USER" -d "$scratch" -c "
        select 'themes' as таблица, count(*) from themes
        union all select 'source_channels', count(*) from source_channels
        union all select 'candidate_posts', count(*) from candidate_posts
        union all select 'post_versions', count(*) from post_versions
        union all select 'publications', count(*) from publications
        union all select 'target_channels', count(*) from target_channels
        union all select 'channel_bots', count(*) from channel_bots
        union all select 'telethon_sessions', count(*) from telethon_sessions;"
    log "проверка пройдена"
}

make_backup() {
    mkdir -p "$BACKUP_DIR"
    local file="$BACKUP_DIR/nxai-$(date +'%Y-%m-%d-%H%M').sql.gz"

    log "снимаю дамп → $file"
    # pipefail включён выше: если pg_dump упадёт, gzip всё равно создаст файл, но
    # скрипт остановится и файл ниже не пройдёт проверку.
    $DC exec -T postgres pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$file"

    # Две проверки, и обе нужны. gzip -t ловит обрыв записи (кончился диск), а
    # завершающая строка pg_dump ловит обрыв самого дампа: файл при этом остаётся
    # валидным архивом валидного, но неполного SQL.
    gzip -t "$file" || die "архив побит: $file"
    gunzip -c "$file" | tail -5 | grep -q "PostgreSQL database dump complete" \
        || die "дамп оборван (нет завершающей строки pg_dump): $file"

    log "готово, размер $(du -h "$file" | cut -f1)"

    if [ -n "$OFFSITE_CMD" ]; then
        log "копия вне сервера: $OFFSITE_CMD $file"
        $OFFSITE_CMD "$file"
    else
        log "ВНИМАНИЕ: OFFSITE_CMD не задан — копия только на этом сервере."
        log "Потеря сервера = потеря бэкапа."
    fi

    log "убираю дампы старше $KEEP_DAYS дней"
    find "$BACKUP_DIR" -name 'nxai-*.sql.gz' -mtime +"$KEEP_DAYS" -print -delete
}

case "${1:-}" in
    --restore-check) restore_check ;;
    "")              make_backup ;;
    *)               die "неизвестный аргумент: $1 (ожидается пусто или --restore-check)" ;;
esac
