FROM ghcr.io/astral-sh/uv:0.11.9 AS uv-bin

FROM python:3.11-slim

WORKDIR /app

# Copy uv binary from official image — avoids pip/PyPI download entirely
COPY --from=uv-bin /uv /uvx /usr/local/bin/

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock .python-version README.md ./

# Install production dependencies only
RUN uv sync --frozen --no-dev

# Copy application source and migration files
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Railway injects PORT; fall back to 8080
CMD ["sh", "-c", "uv run uvicorn fastapistock.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
