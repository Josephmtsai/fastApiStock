# Quickstart: fastApiStock

**Date**: 2026-04-03

## Prerequisites

- Python 3.11+
- [UV](https://docs.astral.sh/uv/) installed

## Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd fastApiStock

# 2. Install dependencies
uv sync

# 3. Copy and fill environment variables
cp .env.example .env
# Edit .env: set TW_STOCK_API_BASE_URL and other vars

# 4. Start the development server
uv run uvicorn src.main:app --reload
```

## Validation

```bash
# Health check
curl http://localhost:8000/health
# → {"status":"success","data":{"status":"ok"},"message":""}

# Stock quote (Taiwan Semiconductor)
curl http://localhost:8000/stocks/2330

# Historical data (last 7 days)
curl "http://localhost:8000/stocks/2330/history?limit=7"
```

## Run Tests

```bash
uv run pytest
# With coverage report
uv run pytest --cov=src --cov-report=term-missing
```

## Lint & Type Check

```bash
uv run ruff check . --fix && uv run ruff format .
uv run mypy src/
```

## Pre-commit (required before every commit)

```bash
uv run pre-commit run --all-files
```

## Project Layout Quick Reference

```
src/
├── main.py          → app factory + router registration
├── config.py        → Settings from .env
├── dependencies.py  → shared Depends()
├── exceptions.py    → exception handlers
├── routers/         → APIRouter modules (one per domain)
├── schemas/         → Pydantic models (request/response)
├── services/        → business logic
├── repositories/    → external API calls (timeout + delay)
└── cache/           → local file cache
```
