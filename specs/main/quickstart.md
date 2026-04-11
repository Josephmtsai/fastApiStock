# Quickstart: fastApiStock

**Date**: 2026-04-06

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

# 4. Start the development server (from repo root)
uv run uvicorn src.fastapistock.main:app --reload
```

## Validation

```bash
# Health check
curl http://localhost:8000/health
# → {"status":"success","data":{"status":"ok"},"message":""}

# API index (lists routes)
curl http://localhost:8000/

# Stock quotes (comma-separated codes)
curl http://localhost:8000/api/v1/stock/2330,0050

# Telegram push (example — requires bot configuration)
curl "http://localhost:8000/api/v1/tgMessage/12345?stock=2330"

# Test /pnl webhook command (requires TELEGRAM_WEBHOOK_SECRET set)
curl -X POST http://localhost:8000/api/v1/webhook/telegram \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: <secret>" \
  -d '{"update_id":1,"message":{"message_id":1,"from":{"id":<TELEGRAM_USER_ID>,"is_bot":false,"first_name":"Test"},"chat":{"id":<TELEGRAM_USER_ID>},"text":"/pnl"}}'
# → {"status":"success","data":null,"message":"ok"}  (bot sends reply to chat)
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

```text
src/fastapistock/
├── main.py              → app factory + middleware + routers
├── config.py            → Settings from .env
├── exceptions.py        → exception handlers
├── routers/             → APIRouter per domain
├── schemas/             → Pydantic models
├── services/            → business orchestration
├── repositories/        → external I/O (timeouts, delays)
├── cache/               → Redis cache (redis-py)
└── middleware/          → rate limit, structured logging (REQ/RES/PERF)
```
