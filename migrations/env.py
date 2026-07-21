import asyncio
from logging.config import fileConfig

from pgvector.sqlalchemy import Vector
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from alembic.autogenerate.api import AutogenContext

from core.config import get_settings
from core.models import Base

config = context.config

# DATABASE_URL приходит из core.config.Settings (.env), а не из alembic.ini —
# единая точка конфигурации для core/interfaces/migrations.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метаданные всех моделей ядра (core/models/__init__.py) — источник для autogenerate.
target_metadata = Base.metadata


def render_item(type_: str, obj: object, autogen_context: AutogenContext) -> str | bool:
    """Известный баг связки Alembic+pgvector: autogenerate рендерит колонку как
    `pgvector.sqlalchemy.vector.VECTOR(...)`, но не добавляет для неё import —
    сгенерированная миграция падает `NameError: name 'pgvector' is not defined`
    при первом же upgrade. Явно рендерим Vector(...) и просим добавить нужный
    import в шапку файла (autogen_context.imports — множество строк, которые
    alembic вставляет в ${imports} шаблона migrations/script.py.mako)."""
    if type_ == "type" and isinstance(obj, Vector):
        autogen_context.imports.add("from pgvector.sqlalchemy import Vector")
        return f"Vector({obj.dim})"
    return False


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_item=render_item)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
