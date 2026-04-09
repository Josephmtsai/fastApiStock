# Research: FastAPI Project Folder Structure

**Date**: 2026-04-06
**Status**: Aligned with `specs/main/spec.md` and constitution v1.2.0

## Decisions

| Topic | Decision | Rationale | Alternatives Considered |
|-------|----------|-----------|------------------------|
| Cache backend | **Redis** (`redis-py`) | Constitution IV — single cache layer; shared across Uvicorn workers | File JSON cache (**rejected** — parallel cache forbidden), in-memory only (**rejected** — not shared) |
| Rate limiting | **Redis-backed** middleware | Constitution III; consistent limits across workers; config via env | Per-process memory limiter (**rejected** for multi-worker) |
| Auth | None in v1 | Spec assumptions; rate limiting + logging | JWT / API keys — deferred |
| Pydantic version | v2 (via FastAPI) | `pyproject.toml` | Pydantic v1 (legacy) |
| ORM / DB | None in v1 | External TW data + Redis | SQLAlchemy — deferred |
| Package layout | `src/fastapistock/` | PEP 517 src layout; clean imports | Flat `src/routers/` (**obsolete** in this repo) |

## FastAPI Best-Practice Sources

- [FastAPI bigger applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/) — `APIRouter` modules
- [Full-stack FastAPI template](https://github.com/fastapi/full-stack-fastapi-template) — layering ideas (`schemas/`, services, core config)

## Key Findings

1. **`main.py` should only** wire `create_app()`, middleware order, `include_router`, and exception
   registration — no business rules.
2. **`middleware/`** holds cross-cutting HTTP concerns (rate limit, structured logging) per
   constitution V and Security Constraints.
3. **`repositories/`** holds external I/O; **services/** orchestrate cache + repositories.
4. **Performance**: reuse clients (HTTP pool, Redis connection) where hot paths warrant it; batch
   multi-symbol work in the service layer (see spec § Performance & Acceleration).
