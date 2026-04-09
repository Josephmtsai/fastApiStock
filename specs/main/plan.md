# Implementation Plan: FastAPI Project Folder Structure

**Branch**: `main` | **Date**: 2026-04-06 | **Spec**: `specs/main/spec.md`
**Input**: Feature specification from `specs/main/spec.md`

## Summary

Establish the canonical folder layout for `fastApiStock` — a Taiwan stock data REST API built with
FastAPI. The structure isolates routing, schema, business logic, data-fetch, **middleware**
(cross-cutting), and **Redis-backed** cache/rate-limit infrastructure under the installable package
`fastapistock`, following PEP 517 src layout, FastAPI community practice, and the project
constitution (Principles I–V).

## Technical Context

**Language/Version**: Python 3.11 (`.python-version`)
**Primary Dependencies**: FastAPI 0.135+, Uvicorn, httpx, python-dotenv, Pydantic v2, **redis-py**
**Storage**: **Redis** (cache + rate limit state); no relational DB in v1
**Testing**: pytest + pytest-cov + httpx (async test client); fakeredis where integration tests need
Redis without a live server
**Target Platform**: Linux server (Docker-compatible)
**Project Type**: web-service (JSON REST API)
**Performance Goals**: ≤ 200 ms p95 for cached endpoints; ≤ 2 s for live-fetch endpoints (constitution
IV); reuse connection pools for HTTP/Redis on hot paths (spec P-002, P-005)
**Constraints**: External TW stock APIs require random delay 0.5–2 s between calls; explicit
`timeout` on all outgoing requests; Redis rate limiting; graceful degradation if Redis is down
(constitution IV); structured REQ/RES/PERF logging (constitution V)
**Scale/Scope**: Single-developer project; small route surface; designed to add domains without
touching unrelated modules

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| **I. Code Quality** | Typed public API, docstrings, ruff + mypy, config externalised | ✅ FR-005, FR-011 |
| **II. Testing Standards** | `tests/unit/` + `tests/integration/`; 80%+ coverage | ✅ Spec SC-002 |
| **III. API Consistency** | `APIRouter` only; envelope in `schemas/common.py`; Redis rate limit | ✅ FR-001, FR-007, FR-008 |
| **IV. Performance & Resilience** | Timeouts + delay in repos; **Redis-only** cache; no parallel file cache; fallback | ✅ FR-009, FR-011 |
| **V. Observability** | Single middleware: REQ / RES / PERF log format | ✅ FR-010 |

**Result**: PASS when implementation matches spec + constitution. Re-run this gate after any
structural change.

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
│   └── fastapistock/           # Installable package (PEP 517)
│       ├── main.py             # create_app(), middleware order, include_router()
│       ├── config.py           # Settings from env
│       ├── exceptions.py       # Exception handlers registration
│       ├── routers/            # One APIRouter per domain
│       │   ├── health.py       # GET /health
│       │   ├── stocks.py       # GET /api/v1/stock/{id}
│       │   ├── telegram.py     # GET /api/v1/tgMessage/{id}
│       │   └── index.py        # GET / — API index (optional)
│       ├── schemas/
│       │   ├── common.py       # ResponseEnvelope[T]
│       │   └── stock.py        # StockData, …
│       ├── services/           # Business orchestration
│       ├── repositories/       # External I/O (yfinance, HTTP, …)
│       ├── cache/              # Redis cache helper (redis-py only)
│       └── middleware/
│           ├── logging.py      # REQ / RES / PERF (constitution V)
│           └── rate_limit/     # Redis sliding window + block
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── integration/
│
├── .env.example
├── pyproject.toml
├── uv.lock
└── .python-version
```

**Structure Decision**: **Src layout** with package name `fastapistock`. Cross-cutting HTTP concerns
live in `middleware/`; domain code stays in `routers/`, `services/`, `repositories/`. Tests live under
`tests/` and mirror behaviour, not necessarily every subfolder name.

## Complexity Tracking

> No constitution violations detected — section left intentionally blank.

---

## Phase 0: Research

| Unknown | Decision | Rationale |
|---------|----------|-----------|
| Cache + rate limit backend | **Redis** (`redis-py`) | Constitution IV; single source of truth; works across Uvicorn workers |
| Parallel file cache | **Not allowed** | Constitution IV — no second cache layer |
| Auth | None in v1 | Spec assumptions; abuse handled by rate limiting |
| Pydantic version | v2 | FastAPI dependency |
| DB ORM | None in v1 | External APIs + Redis only |

**Output**: Captured above; see `research.md` for any deeper notes.

---

## Phase 1: Design & Contracts

### Data Model (`data-model.md`)

Key entities under `src/fastapistock/schemas/`:

| Entity | Location | Purpose |
|--------|----------|---------|
| `ResponseEnvelope[T]` | `schemas/common.py` | `{status, data, message}` |
| `StockData` | `schemas/stock.py` | Quote snapshot for `/api/v1/stock/{id}` |
| `Settings` | `config.py` | Env-driven configuration |

### Contracts (`contracts/`)

| Route | Method | Response (shape) |
|-------|--------|------------------|
| `/` | `GET` | API index (`ResponseEnvelope` list of routes) |
| `/health` | `GET` | `ResponseEnvelope[{"status": "ok"}]` |
| `/api/v1/stock/{id}` | `GET` | `ResponseEnvelope[list[StockData]]` |
| `/api/v1/tgMessage/{id}` | `GET` | `ResponseEnvelope` (Telegram push result) |

Success and error bodies use the same envelope; HTTP status codes follow constitution III.

### Layer Responsibilities

```text
HTTP Request
    → Middleware (rate limit → logging REQ)
    → Router (thin)
    → Service (orchestration)
    → Repository (external API + polite delays + timeouts)
    → Redis cache (read-through / write-through; graceful skip on failure)
    → Middleware (logging RES + PERF)
    → HTTP Response
```

- **Router**: Validate/coerce input, call service, return envelope.
- **Service**: Orchestrate cache ↔ repository; batch multi-symbol work in one service call where
  possible (spec P-004).
- **Repository**: External calls only; enforce timeouts and inter-request delay policy.
- **Cache**: Redis via `redis-py`; TTL and keys from config/env.
- **Middleware**: Rate limiting and structured logging — not duplicated in routes.

---

## Next Step

Run `/speckit-tasks` against this plan to generate `specs/main/tasks.md` with concrete implementation
tasks ordered by user story priority.
