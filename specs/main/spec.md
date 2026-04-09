# Feature Specification: FastAPI Project Folder Structure

**Feature Branch**: `main`
**Created**: 2026-04-03
**Status**: Draft (aligned with constitution v1.2.0)
**Input**: User description: "請根據 FastAPI best practice 列出資料夾格式"

**Normative reference**: All structural and non-functional rules below MUST remain consistent with
[`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) (Principles I–V). If this
spec ever conflicts with the constitution, the constitution wins.

---

## Alignment Notes (what changed vs. earlier draft)

The original draft assumed a **flat** `src/` tree (`src/routers/`, `src/main.py`) and **local file
cache**. The implemented codebase uses a **src-layout installable package** `fastapistock` and
**Redis** for cache and rate limiting, plus **middleware** for cross-cutting concerns. This document
is updated to match reality and the constitution.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Developer can navigate source code intuitively (Priority: P1)

A developer joining the project can locate any router, schema, service, or repository by following a
predictable, convention-based layout — without needing to grep the whole tree.

**Why this priority**: An agreed-upon structure is the foundation every other feature builds on;
wrong structure causes refactoring debt immediately.

**Independent Test**: Clone the repo, run
`uv run uvicorn fastapistock.main:app --reload` (or `uv run uvicorn src.fastapistock.main:app --reload`
depending on `PYTHONPATH`), hit `GET /health` → 200 OK. No route logic exists in `main.py` beyond
`include_router` and app wiring.

**Acceptance Scenarios**:

1. **Given** the project root, **When** a developer looks for stock-related routes,
   **Then** they find them in `src/fastapistock/routers/stocks.py`.
2. **Given** the project root, **When** a developer looks for response shapes,
   **Then** they find Pydantic models in `src/fastapistock/schemas/`.
3. **Given** the project root, **When** a developer looks for data-fetch logic,
   **Then** they find it in `src/fastapistock/repositories/`, not inside route handlers.
4. **Given** the project root, **When** a developer looks for rate limiting or access logging,
   **Then** they find them under `src/fastapistock/middleware/`, not duplicated per route.

---

### User Story 2 - Tests are co-located and easy to run (Priority: P2)

A developer can run `uv run pytest` from the project root and all unit + integration tests are
discovered automatically.

**Why this priority**: Testability is a constitution non-negotiable; the folder structure must support
it from day one.

**Independent Test**: `uv run pytest --co -q` lists tests without errors.

**Acceptance Scenarios**:

1. **Given** the `tests/` directory, **When** pytest runs, **Then** unit tests in `tests/unit/` and
   integration tests in `tests/integration/` are all collected.
2. **Given** a new router file, **When** the developer adds `tests/integration/test_<router>.py`,
   **Then** pytest picks it up with no configuration change.

---

### Edge Cases

- **New domain** (e.g. `options/`): add `src/fastapistock/routers/options.py`,
  `src/fastapistock/schemas/option.py`, `src/fastapistock/services/option_service.py`,
  `src/fastapistock/repositories/options_repo.py` — prefer no edits to unrelated modules.
- **Shared FastAPI wiring**: `Depends()` factories in `src/fastapistock/dependencies.py` (when
  needed); exception handlers in `src/fastapistock/exceptions.py`.
- **Cross-cutting**: rate limiting, structured logging, and future auth hooks live in
  `src/fastapistock/middleware/` — not inside individual route functions.
- **Redis unavailable**: API MUST degrade gracefully (constitution IV); document expected behaviour
  per endpoint (e.g. bypass cache, still return 200 with live data where possible).

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Routes MUST be defined under `src/fastapistock/routers/` via `APIRouter`, never as
  large inline route trees in `main.py` (wiring only: `create_app()`, `include_router`, middleware).
- **FR-002**: Pydantic request/response models MUST live in `src/fastapistock/schemas/`.
- **FR-003**: Business logic MUST live in `src/fastapistock/services/`; route handlers MUST only
  orchestrate (validate, call service, map to envelope).
- **FR-004**: External data-fetch logic (TW stock APIs, HTTP, Redis I/O) MUST live in
  `src/fastapistock/repositories/` or dedicated infrastructure modules (e.g. `cache/`), not in
  routers.
- **FR-005**: App settings MUST be loaded via a `Settings` (or equivalent) class in
  `src/fastapistock/config.py` using `python-dotenv` / environment variables — no magic numbers in
  business code (constitution I).
- **FR-006**: Shared `Depends()` callables MUST live in `src/fastapistock/dependencies.py` when they
  are reused across routers.
- **FR-007**: All API JSON responses MUST use the envelope `ResponseEnvelope[T]` from
  `src/fastapistock/schemas/common.py` unless raw streaming is explicitly specified (out of scope
  for v1).
- **FR-008**: Rate limiting MUST be enforced consistently (constitution III / Security Constraints)
  using the project’s Redis-backed mechanism; configuration MUST come from env vars (see
  `.env.example`), not hardcoded limits.
- **FR-009**: Application caching MUST use **Redis via `redis-py`** only; parallel file-based or ad
  hoc in-memory TTL caches alongside Redis are PROHIBITED (constitution IV).
- **FR-010**: Observability MUST follow constitution Principle V: one middleware emits structured
  REQ / RES / PERF log lines for every API; routes MUST NOT each implement their own log format.
- **FR-011**: Outbound HTTP and Redis clients MUST use explicit timeouts; on dependency failure the
  service MUST not hang indefinitely (constitution IV).

### Architecture Conventions (Python / FastAPI best practice)

- **Src layout**: The importable package is `fastapistock` under `src/fastapistock/` (PEP 517 wheel
  via `pyproject.toml`). Tests and tools use `src/` on the path or the installed package name.
- **Application factory**: `create_app()` in `main.py` returns a configured `FastAPI` instance
  (easier testing and multiple app instances in tests).
- **Thin routers**: Routers parse/validate input and delegate; no heavy logic or direct external
  calls.
- **Lifespan (optional extension)**: Shared clients (e.g. Redis connection pool, `httpx` client) MAY
  be opened in `lifespan` context and injected via `Depends()` or an app-state holder — avoids
  per-request connection churn when traffic grows.
- **Single responsibility**: Keep modules small; constitution I caps public functions at 50 lines
  where practical.

### Performance & Acceleration *(non-functional)*

These targets align with constitution IV and common FastAPI deployment practice:

- **P-001 (cache)**: Prefer Redis hits for repeated reads; TTLs and keys MUST be configurable via env
  / config, not literals in code.
- **P-002 (network)**: Reuse HTTP clients (connection pooling) for outbound calls; avoid creating a
  new `httpx` client per request in hot paths.
- **P-003 (async)**: Use `async` route handlers when the stack awaits I/O; keep CPU-bound work off
  the event loop or run in a thread pool if introduced later.
- **P-004 (batching)**: When one request asks for multiple symbols, batch repository calls inside the
  service layer instead of N sequential router round-trips.
- **P-005 (process model)**: Document production deployment: multiple Uvicorn workers for CPU-bound
  JSON serialization load; Redis as shared store for rate limit + cache across workers.
- **P-006 (edge)**: Terminate TLS and gzip at a reverse proxy (nginx, Caddy, cloud LB); keep the app
  focused on business latency (optional but recommended for production).

### Key Entities

- **Router**: `APIRouter` scoped to one domain (stocks, health, telegram, index, …).
- **Schema**: Pydantic model for validation or response serialization.
- **Service**: Pure orchestration / business rules; no low-level HTTP client usage unless the team
  explicitly standardises on a thin HTTP wrapper in repositories only.
- **Repository**: External I/O (HTTP, Redis commands) with timeouts, retries policy, and polite
  delays where required by upstream.
- **Middleware**: Cross-cutting HTTP concerns (rate limit, access + performance logging).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `uv run uvicorn src.fastapistock.main:app` (from repo root with `src` layout) or
  equivalent documented command starts without import errors.
- **SC-002**: `uv run pytest` collects and passes all tests (target ≥ 80% coverage).
- **SC-003**: `uv run ruff check . && uv run mypy src/` both exit 0.
- **SC-004**: Adding a new domain requires touching only new files under the usual layers (router,
  schema, service, repository) without mandatory edits to unrelated domains.
- **SC-005**: Under normal conditions, cached read endpoints meet constitution guidance (≈200 ms);
  live-fetch paths complete within ≈2 s p95 excluding upstream outages.

---

## Assumptions

- No frontend; JSON REST API consumed by other services or scripts.
- No relational database in v1; persistence is Redis (cache + rate limit metadata) plus external TW
  stock data sources.
- Authentication/authorization is out of scope for v1 (rate limiting + logging only).
- A single `ResponseEnvelope` generic type covers all success and error responses for JSON APIs.
- Production expects Redis available; development MAY use fakeredis or local Redis with graceful
  degradation behaviour defined per feature.
