# Research: FastAPI Project Folder Structure

**Date**: 2026-04-03
**Status**: Complete — all unknowns resolved from existing project context

## Decisions

| Topic | Decision | Rationale | Alternatives Considered |
|-------|----------|-----------|------------------------|
| Cache backend | Local file cache (JSON) | MVP; no infra dependency; satisfies Constitution Principle IV | Redis (over-engineered for v1), in-memory dict (lost on restart) |
| Auth | None in v1 | Out of scope (spec Assumptions); rate limiting covers abuse | JWT, API keys — deferred to v2 |
| Pydantic version | v2 (via FastAPI ≥ 0.100) | Already pinned in `pyproject.toml` | Pydantic v1 (legacy) |
| ORM / DB | None in v1 | Data comes from TW stock external APIs + file cache only | SQLAlchemy (premature for external-API-first design) |
| Rate limiting | `slowapi` or custom `Depends()` middleware | Must be at router level per constitution; no external infra needed | Redis-backed rate limiter (v2 option) |

## FastAPI Best-Practice Sources

- [FastAPI official project structure guide](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
  → confirms `routers/` + `APIRouter` pattern
- [Full-stack FastAPI template](https://github.com/fastapi/full-stack-fastapi-template)
  → confirms `schemas/`, `crud/` (→ renamed `repositories/` here), `core/` (→ `config.py` + `dependencies.py`)
- Project constitution Principle III: all routes via `APIRouter`, never `main.py`

## Key Findings

1. **`main.py` should only**: create the `FastAPI()` app, register routers, configure middleware/exception
   handlers, and define `lifespan`. Zero business logic.
2. **`schemas/` vs `models/`**: In DB-less projects, `schemas/` holds all Pydantic models.
   `models/` is reserved for ORM layer (not needed in v1).
3. **`repositories/` not `crud/`**: The `crud/` naming implies CRUD-on-DB. Since v1 is external-API
   + file-cache, `repositories/` better expresses intent.
4. **`dependencies.py`**: Centralizing `Depends()` prevents scattered dependency definitions and
   makes testing easier (override with `app.dependency_overrides`).
