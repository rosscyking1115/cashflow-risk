# API image — uv-based, reproducible. Applies migrations on start, then serves.
FROM python:3.12-slim

# uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Dependencies first, for layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application source + migrations.
COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000
# $PORT is provided by the platform; fall back to 8000 locally.
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn cashflow_risk.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
