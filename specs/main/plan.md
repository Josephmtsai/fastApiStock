# Implementation Plan: FastAPI Project Folder Structure

**Branch**: `main` | **Date**: 2026-04-03 | **Spec**: `specs/main/spec.md`
**Input**: Feature specification from `specs/main/spec.md`

## Summary

Establish the canonical folder layout for `fastApiStock` — a Taiwan stock data
REST API built with FastAPI. The structure isolates routing, schema, business
logic, and data-fetch concerns into discrete directories, following FastAPI
community best practices and the project constitution (Principles I–IV).

## Technical Context

**Language/Version**: Python 3.11 (`.python-version`)
**Primary Dependencies**: FastAPI 0.135+, Uvicorn, httpx, python-dotenv, Pydantic v2
**Storage**: Local file cache (JSON/pickle); no relational DB in v1
**Testing**: pytest + pytest-cov + httpx (async test client)
**Target Platform**: Linux server (Docker-compatible)
**Project Type**: web-service (JSON REST API)
**Performance Goals**: ≤ 200 ms p95 for cached endpoints; ≤ 2 s for live-fetch endpoints
**Constraints**: External TW stock APIs require random delay 0.5–2 s between calls; explicit
`timeout` on all outgoing requests; rate limiting on all routes
**Scale/Scope**: Single-developer project; ~10 route endpoints at launch; designed to add
domains without touching existing files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| **I. Code Quality** | All public functions typed + docstrings; ruff + mypy pass; no `print()`/`Any` | ✅ Structure enforces this via `src/` layout |
| **II. Testing Standards** | `tests/unit/` + `tests/integration/` directories; 80%+ coverage | ✅ Defined in spec SC-002 |
| **III. API Consistency** | All routes via `APIRouter`; envelope `{status, data, message}` in `schemas/common.py` | ✅ FR-001, FR-008 |
| **IV. Performance & Resilience** | Timeout + random delay in `repositories/`; cache in `src/cache/` | ✅ FR-004, FR-005 |

**Result**: PASS — no violations. No Complexity Tracking entry required.

## Project Structure

### Documentation (this feature)

```text
specs/main/
├── plan.md          # This file
├── spec.md          # Feature specification
├── research.md      # Phase 0 output
├── data-model.md    # Phase 1 output
├── quickstart.md    # Phase 1 output
└── contracts/       # Phase 1 output
```

### Source Code (repository root)

```text
fastApiStock/
├── src/
│   ├── __init__.py
│   ├── main.py              # App factory: create_app(), lifespan, include_router()
│   ├── config.py            # Settings (pydantic-settings / python-dotenv)
│   ├── dependencies.py      # Shared Depends(): rate_limiter, get_cache, …
│   ├── exceptions.py        # Custom exception classes + FastAPI exception_handler()
│   │
│   ├── routers/             # One APIRouter per domain
│   │   ├── __init__.py
│   │   ├── health.py        # GET /health
│   │   └── stocks.py        # GET /stocks/{symbol}, GET /stocks/{symbol}/history, …
│   │
│   ├── schemas/             # Pydantic v2 models (no SQLAlchemy here)
│   │   ├── __init__.py
│   │   ├── common.py        # ResponseEnvelope[T], ErrorDetail
│   │   └── stock.py         # StockQuote, StockHistory, StockQueryParams
│   │
│   ├── services/            # Business logic — no HTTP imports
│   │   ├── __init__.py
│   │   └── stock_service.py # StockService: get_quote(), get_history()
│   │
│   ├── repositories/        # External data access (httpx, files)
│   │   ├── __init__.py
│   │   └── twstock_repo.py  # TwStockRepository: fetch with timeout + random delay
│   │
│   └── cache/               # Local cache abstraction
│       ├── __init__.py
│       └── file_cache.py    # FileCache: get(), set(), invalidate()
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Fixtures: test_client, mock_cache, mock_repo
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_stock_service.py
│   │   └── test_file_cache.py
│   └── integration/
│       ├── __init__.py
│       ├── test_health.py
│       └── test_stocks.py
│
├── .env.example             # Template for required env vars
├── .env                     # Local secrets (gitignored)
├── pyproject.toml
├── uv.lock
├── CLAUDE.md
└── .python-version
```

**Structure Decision**: Single-project layout (Option 1). No frontend, no mobile.
`src/` is the importable package root; `tests/` mirrors it. Each concern layer is
in its own directory — adding a new domain (e.g., `options`) requires only new
files in `routers/`, `schemas/`, `services/`, `repositories/`.

## Complexity Tracking

> No constitution violations detected — section left intentionally blank.

---

## Phase 0: Research

*Resolved during planning — no external research required for a structural decision.*

| Unknown | Decision | Rationale |
|---------|----------|-----------|
| Cache backend | Local file cache (JSON) | No Redis dependency; MVP; constitution Principle IV |
| Auth | None in v1 | Out of scope per spec Assumptions; rate limiting covers abuse |
| Pydantic version | v2 (bundled with FastAPI 0.100+) | Already in `pyproject.toml` via FastAPI dep |
| DB ORM | None in v1 | External API + file cache only; spec Assumption |

**Output**: No `research.md` needed — all unknowns resolved from existing `pyproject.toml`
and spec Assumptions. A `research.md` stub is created for traceability.

---

## Phase 1: Design & Contracts

### Data Model (`data-model.md`)

Key entities derived from `src/schemas/`:

| Entity | Location | Purpose |
|--------|----------|---------|
| `ResponseEnvelope[T]` | `schemas/common.py` | Wraps all responses: `{status, data, message}` |
| `ErrorDetail` | `schemas/common.py` | Structured error body |
| `StockQuote` | `schemas/stock.py` | Real-time quote data |
| `StockHistory` | `schemas/stock.py` | Historical OHLCV records |
| `StockQueryParams` | `schemas/stock.py` | Query string validation |
| `Settings` | `config.py` | App config loaded from `.env` |

### Contracts (`contracts/`)

| Route | Method | Response |
|-------|--------|---------|
| `/health` | `GET` | `ResponseEnvelope[{"status": "ok"}]` |
| `/stocks/{symbol}` | `GET` | `ResponseEnvelope[StockQuote]` |
| `/stocks/{symbol}/history` | `GET` | `ResponseEnvelope[list[StockHistory]]` |

All routes return HTTP 200 on success and HTTP 4xx/5xx with `ResponseEnvelope[null]`
(`status: "error"`, `message: <reason>`) on failure.

### Layer Responsibilities

```
Request → Router → Service → Repository → External API / Cache
                           ↓
                     (cache hit) → return immediately
```

- **Router**: validate input (Pydantic), call service, return envelope.
- **Service**: orchestrate cache check → repo fetch → cache write.
- **Repository**: HTTP call with `timeout=10`, random sleep 0.5–2 s, structured logging.
- **Cache**: file-based JSON store keyed by `(symbol, date)`.

---

## Next Step

Run `/speckit-tasks` against this plan to generate `specs/main/tasks.md` with
concrete implementation tasks ordered by user story priority.
