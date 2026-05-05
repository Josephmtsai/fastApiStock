FROM python:3.11-slim

WORKDIR /app

# Install uv via pip — bypasses mise/aqua/attestation entirely
RUN pip install --no-cache-dir uv==0.11.9

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock .python-version ./

# Install production dependencies only
RUN uv sync --frozen --no-dev

# Copy application source and migration files
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Railway injects PORT; fall back to 8080
CMD ["sh", "-c", "uv run uvicorn fastapistock.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
