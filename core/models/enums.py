import enum


class BotRole(str, enum.Enum):
    """Роль записи в channel_bots: THEME — публикующий бот одной тематики
    (свой tg-токен, свой персонаж/стиль, свой целевой канал); ADMIN — ровно
    одна запись, агрегирующий бот для оператора (уведомления+статистика по
    всем темам, см. core/services/admin_notify.py)."""

    THEME = "theme"
    ADMIN = "admin"


class CandidatePostStatus(str, enum.Enum):
    """Жизненный цикл поста-кандидата (core/models/candidate_post.py), в
    отличие от NX Draft — кандидат НЕ готов к публикации сразу, он должен
    дозреть по метрикам и пройти дедуп/рерайт, прежде чем попасть в пул."""

    NEW = "new"                # только что увиден ingest-воркером
    SCORING = "scoring"        # ждёт очередного снапшота метрик (+30м/+2ч/+6ч)
    SELECTED = "selected"      # score прошёл порог, дедуп подтвердил уникальность
    REWRITTEN = "rewritten"    # LLM-рерайт создан (post_versions), готов для автопаблиш-пула
    PENDING_REVIEW = "pending_review"  # рерайт создан принудительно ("Сделать посты" в панели,
                                       # core/services/force_generate.py) — ждёт ручного
                                       # approve/reject (core/services/review.py) прежде чем
                                       # стать обычным REWRITTEN и попасть в автопаблиш-шафл
    QUEUED = "queued"          # взят планировщиком в конкретный публикационный слот
    PUBLISHED = "published"
    REJECTED = "rejected"      # не прошёл скоринг/дедуп либо отклонён вручную в панели
    DUPLICATE = "duplicate"    # свёрнут в другой candidate_post (duplicate_of_id)


class PoolPostStatus(str, enum.Enum):
    READY = "ready"
    USED = "used"


class PoolPostSource(str, enum.Enum):
    MANUAL = "manual"                  # добавлен вручную из панели
    GENERATED = "generated"            # проактивно сгенерирован LLM (evergreen)
    RECYCLED_CANDIDATE = "recycled"    # хорошо показавший себя кандидат, оставленный про запас


class PublicationSource(str, enum.Enum):
    CANDIDATE = "candidate"    # опубликован рерайт кандидата из тематического пайплайна
    POOL = "pool"              # опубликован пост из pool_posts (обычное заполнение либо ad-cover)


class AdDetectionAction(str, enum.Enum):
    PENDING = "pending"            # обнаружено, таймер на 60 минут ещё не сработал
    AUTO_BURIED = "auto_buried"    # свой пост из пула поставлен поверх автоматически
    IGNORED = "ignored"            # не перекрыт (например, канал уже неактивен)


class AuditAction(str, enum.Enum):
    INGEST = "ingest"
    SCORE = "score"
    DEDUP_MERGE = "dedup_merge"
    REWRITE = "rewrite"
    PUBLISH = "publish"
    REJECT = "reject"
    AD_DETECTED = "ad_detected"
    AD_COVERED = "ad_covered"
    SETTINGS_CHANGE = "settings_change"
    LOGIN = "login"
    APPROVE = "approve"
    BOT_TOKEN_CHANGE = "bot_token_change"
