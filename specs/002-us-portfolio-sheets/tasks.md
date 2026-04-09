# Tasks: US Portfolio Sheets Integration

**Input**: Design documents from `/specs/002-us-portfolio-sheets/`
**Branch**: `002-us-portfolio-sheets`

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: can run in parallel
- **[Story]**: mapped to user story (`US1` / `US2`)

---

## Phase 1: Setup & Config

**Purpose**: Define environment-driven US/TW sheet GID configuration.

- [ ] T001 Add config variables in `src/fastapistock/config.py`:
  - `GOOGLE_SHEETS_PORTFOLIO_GID_TW`
  - `GOOGLE_SHEETS_PORTFOLIO_GID_US`
  - keep backward compatibility fallback from legacy `GOOGLE_SHEETS_PORTFOLIO_GID`
- [ ] T002 Update `.env.example`:
  - document TW GID and US GID separately
  - keep existing legacy key notes

**Checkpoint**: app startup can read TW/US GID values from environment.

---

## Phase 2: US1 - US message includes portfolio block (Priority: P1)

**Goal**: `/api/v1/usMessage/{id}` shows portfolio data per matched US symbol.

- [ ] T003 [US1] Extend portfolio repository to fetch US sheet by `GOOGLE_SHEETS_PORTFOLIO_GID_US`.
- [ ] T004 [US1] Implement symbol normalization for A-column prefixed symbols:
  - `US_AAPL -> AAPL`
  - `NASDAQ:AAPL -> AAPL`
  - `NYSE-MSFT -> MSFT`
- [ ] T005 [US1] Parse US fields:
  - `A=symbol_with_prefix`
  - `F=shares`
  - `G=avg_cost`
  - `H=unrealized_pnl`
- [ ] T006 [US1] Merge US portfolio snapshot into US stock results in `services/us_stock_service.py`.
- [ ] T007 [US1] Render portfolio block in `services/telegram_service.py` for US market when data exists.
  - unrealized PnL line must display `USD` unit.

**Checkpoint**: `GET /api/v1/usMessage/{id}?stock=AAPL` shows portfolio block when entry exists.

---

## Phase 3: US2 - Cache and fallback (Priority: P2)

**Goal**: minimize Sheets calls and ensure resilient behavior.

- [ ] T008 [US2] Add Redis cache key strategy for US portfolio snapshot.
- [ ] T009 [US2] Cache-hit/miss logic in US flow with TTL from `PORTFOLIO_CACHE_TTL`.
- [ ] T010 [US2] Graceful fallback behavior:
  - Redis unavailable -> live Sheets fetch
  - Sheets unavailable/timeout -> skip portfolio block, continue push

**Checkpoint**: two pushes within TTL issue at most one Sheets request.

---

## Phase 4: Scheduler/API split verification

**Purpose**: preserve independent TW/US operational paths.

- [ ] T011 Verify US manual endpoint remains separate:
  - `/api/v1/usMessage/{id}` in `routers/us_telegram.py`
- [ ] T012 Verify scheduler US path remains separate:
  - `push_us_stocks()` in `scheduler.py`
  - no TW-service coupling introduced

---

## Phase 5: Tests

- [ ] T013 [P] Add/extend unit tests for repository parser and normalizer:
  - prefixed symbol normalization
  - malformed row skip
  - comma/negative PnL parsing
- [ ] T014 [P] Add/extend service tests:
  - US merge success
  - no-entry behavior
  - Redis fallback path
- [ ] T015 [P] Add/extend formatter tests:
  - US portfolio block visible when data exists
  - hidden when portfolio data missing
- [ ] T016 Add scheduler/API flow tests for split behavior.

---

## Phase 6: Quality Gates

- [ ] T017 [P] `uv run ruff check . --fix && uv run ruff format .`
- [ ] T018 [P] `uv run mypy src/`
- [ ] T019 `uv run pytest --cov=src --cov-report=term-missing`

---

## Dependencies & Order

```text
Phase1 (config/env)
  -> Phase2 (US portfolio enrichment)
  -> Phase3 (cache/fallback)
  -> Phase4 (split verification)
  -> Phase5 (tests)
  -> Phase6 (quality gates)
```

Parallel candidates:
- T013/T014/T015
- T017/T018 before T019
