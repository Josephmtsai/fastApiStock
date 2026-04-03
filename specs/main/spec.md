# Feature Specification: FastAPI Project Folder Structure

**Feature Branch**: `main`
**Created**: 2026-04-03
**Status**: Draft
**Input**: User description: "請根據 FastAPI best practice 列出資料夾格式"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Developer can navigate source code intuitively (Priority: P1)

A developer joining the project can locate any router, schema, service, or
repository by following a predictable, convention-based layout — without
needing to grep the whole tree.

**Why this priority**: An agreed-upon structure is the foundation every other
feature builds on; wrong structure causes refactoring debt immediately.

**Independent Test**: Clone the repo, run the dev server with `uv run uvicorn src.main:app --reload`,
hit `GET /health` → 200 OK. No route logic exists in `main.py`.

**Acceptance Scenarios**:

1. **Given** the project root, **When** a developer looks for stock-related routes,
   **Then** they find them in `src/routers/stocks.py`.
2. **Given** the project root, **When** a developer looks for response shapes,
   **Then** they find Pydantic models in `src/schemas/`.
3. **Given** the project root, **When** a developer looks for data-fetch logic,
   **Then** they find it in `src/repositories/`, not inside route handlers.

---

### User Story 2 - Tests are co-located and easy to run (Priority: P2)

A developer can run `uv run pytest` from the project root and all unit +
integration tests are discovered automatically.

**Why this priority**: Testability is a constitution non-negotiable; the folder
structure must support it from day one.

**Independent Test**: `uv run pytest --co -q` lists tests without errors.

**Acceptance Scenarios**:

1. **Given** the `tests/` directory, **When** pytest runs, **Then** unit tests in
   `tests/unit/` and integration tests in `tests/integration/` are all collected.
2. **Given** a new router file, **When** the developer adds `tests/integration/test_<router>.py`,
   **Then** pytest picks it up with no configuration change.

---

### Edge Cases

- What happens when a new domain (e.g., `options/`) is added? → Add `src/routers/options.py`,
  `src/schemas/option.py`, `src/services/option_service.py`, `src/repositories/options_repo.py` — no
  changes to existing files required.
- How does the system handle shared utilities? → `src/dependencies.py` for FastAPI `Depends()`;
  `src/exceptions.py` for custom exception classes and handlers.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Routes MUST be defined in `src/routers/` via `APIRouter`, never directly in `main.py`.
- **FR-002**: Pydantic request/response models MUST live in `src/schemas/`.
- **FR-003**: Business logic MUST live in `src/services/`; route handlers MUST only call services.
- **FR-004**: External data-fetch logic (TW stock APIs, files) MUST live in `src/repositories/`.
- **FR-005**: Caching logic MUST be isolated in `src/cache/`.
- **FR-006**: App settings MUST be loaded via a `Settings` class in `src/config.py` using `python-dotenv`.
- **FR-007**: Shared `Depends()` functions MUST be in `src/dependencies.py`.
- **FR-008**: All API responses MUST use the envelope schema `ResponseEnvelope[T]` from `src/schemas/common.py`.

### Key Entities

- **Router**: APIRouter instance scoped to one domain (stocks, health, …).
- **Schema**: Pydantic model for request validation or response serialization.
- **Service**: Pure-Python class/functions containing business logic; no HTTP imports.
- **Repository**: Class that wraps external calls (httpx, files); handles retries, timeouts, delays.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `uv run uvicorn src.main:app` starts without import errors.
- **SC-002**: `uv run pytest` collects and passes all tests (target ≥ 80% coverage).
- **SC-003**: `uv run ruff check . && uv run mypy src/` both exit 0.
- **SC-004**: Adding a new domain requires touching ≤ 4 new files with no changes to existing files.

## Assumptions

- No frontend; this is a pure JSON REST API consumed by other services or scripts.
- No relational database in v1; data comes from TW stock external APIs + local file cache.
- Authentication/authorization is out of scope for v1 (rate limiting only).
- A single `ResponseEnvelope` generic type covers all success and error responses.
