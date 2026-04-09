# Data Model: fastApiStock

**Date**: 2026-04-06

## Schemas (`src/fastapistock/schemas/`)

### `common.py` — Shared envelope

All JSON route handlers return `ResponseEnvelope[<domain_model>]` with shape:

- `status`: `'success' | 'error'`
- `data`: domain payload or `None` on error
- `message`: human-readable detail (empty on success unless documented)

### `stock.py` — Stock domain

| Model | Purpose |
|-------|---------|
| `StockData` | Snapshot for `GET /api/v1/stock/{id}` — fields per implementation (`Name`, `ChineseName`, `price`, `ma20`, `ma60`, `LastDayPrice`, `Volume`, …) |

Historical quote / query-param types are **out of scope** until a route is specified; avoid documenting `StockHistory` here unless implemented.

## Config (`src/fastapistock/config.py`)

Settings MUST be loaded from environment variables (and optional defaults) per constitution I — the
exact field names live in code; this document only states intent:

- External API / timeout / delay bounds
- Redis URL and timeouts
- Rate-limit window / count / block (per route group where applicable)
- Cache TTL for stock payloads

## Cache key convention (Redis)

Keys MUST be namespaced (e.g. prefix `fastapistock:`) and derived from stable inputs (symbol list,
date, endpoint version). Exact key grammar is defined in `cache/` implementation — **not** file paths;
file-based cache directories are obsolete for this project (constitution IV).
