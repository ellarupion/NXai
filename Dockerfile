FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY core ./core
COPY interfaces ./interfaces
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini scheduler.py ./

RUN uv pip install --system --no-cache .

# Команда переопределяется в docker-compose.yml для каждого сервиса
# (ingest / bots / api / scheduler / migrate).
CMD ["python", "-m", "interfaces.bots.main"]
