# Implementation Plan: Portfolio PnL Command (`/pnl`)

**Branch**: `main` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification — add `/pnl` Telegram bot command showing total unrealized profit/loss for TW and US portfolios.

## Summary

Add a `/pnl` command to the Telegram bot that reads two summary cells from Google Sheets
(TW total PnL at I20, US total PnL at H21), both denominated in TWD, and replies with a
formatted breakdown plus combined total.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI, httpx, redis-py, pydantic, python-dotenv
**Storage**: Redis (cache), Google Sheets CSV export (source)
**Testing**: pytest with unittest.mock
**Target Platform**: Linux server (Docker / VPS)
**Project Type**: web-service (FastAPI + Telegram webhook)
**Performance Goals**: Webhook responds within 5 s under normal conditions
**Constraints**: Redis cache TTL reuses `PORTFOLIO_CACHE_TTL`; no new cache mechanism
**Scale/Scope**: Single authorized user; two sheet GIDs; two target cells

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality | ✅ PASS | New row/col constants in `portfolio_repo.py`; no magic numbers in logic |
| II. Testing | ✅ PASS | Unit tests for repo cell-reading + service formatting required |
| III. API Consistency | ✅ PASS | Webhook already returns `ResponseEnvelope`; no new endpoint |
| IV. Performance & Resilience | ✅ PASS | Redis cache with `PORTFOLIO_CACHE_TTL`; `timeout=10` on httpx calls; graceful `None` on error |
| V. Observability | ✅ PASS | Existing webhook middleware handles REQ/RES/PERF logging; no additional logging needed |

**Post-Phase-1 Re-check**: All gates remain PASS — design adds no violations.

## Project Structure

### Documentation (this feature)

```text
specs/main/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
└── contracts/
    └── pnl-command.md   ← Phase 1 output
```

### Source Code Changes

```text
src/fastapistock/
├── repositories/
│   └── portfolio_repo.py          ← add fetch_pnl_tw(), fetch_pnl_us()
├── services/
│   └── portfolio_service.py       ← NEW: get_pnl_reply(), _format_pnl_reply()
└── routers/
    └── webhook.py                 ← add /pnl dispatch + help text

tests/
├── test_portfolio_repo_pnl.py     ← NEW: cell-reading unit tests
└── test_portfolio_service.py      ← NEW: formatting unit tests
```

## Complexity Tracking

> No constitution violations.
