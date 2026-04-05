# Tasks: 20260405 Telegram Info & ChineseName

**Input**: `specs/main/task/20260405task-telegram-info-cache-adjust.md`
**Branch**: `feature/stock`
**Date**: 2026-04-05

## Feature Summary

Extend the FastAPI stock service with two capabilities:
1. Add `ChineseName` field to stock data (both API response and internal model)
2. New `GET /api/v1/tgMessage/{id}?stock={codes}` endpoint that fetches stock data and pushes a formatted Telegram message to the given user ID

**Telegram format per stock:**
```
股票名稱: {ChineseName}
現價: {price}
月均價: {ma20}
季均價: {ma60}
昨天收: {LastDayPrice}
成交量: {Volume}
```

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Add `ChineseName` to the data model and repository — required by both US1 and US2.

- [ ] T001 Add `ChineseName: str` field to `StockData` in `src/fastapistock/schemas/stock.py` (default `''` for cache backward-compat)
- [ ] T002 Update `_build_stock_data()` and `fetch_stock()` in `src/fastapistock/repositories/twstock_repo.py` to populate `ChineseName` from `ticker.info.get('longName', code)`
- [ ] T003 Add `TELEGRAM_TOKEN: str` to `src/fastapistock/config.py` via `os.getenv('TELEGRAM_TOKEN', '')`
- [ ] T004 Add `httpx>=0.28` to production dependencies in `pyproject.toml` (moved from dev group)

---

## Phase 2: US1 — Stock quote includes ChineseName

**Story goal**: `GET /api/v1/stock/{id}` response includes `ChineseName` for each stock.

**Independent test**: `curl http://localhost:8000/api/v1/stock/0050` returns JSON with `ChineseName` field populated.

- [ ] T005 [US1] Verify `ResponseEnvelope[list[StockData]]` in `src/fastapistock/routers/stocks.py` forwards `ChineseName` (no change needed if schema is correct — confirm only)

---

## Phase 3: US2 — Telegram notification endpoint

**Story goal**: `GET /api/v1/tgMessage/{user_id}?stock=0050,2330` fetches stock data and pushes a Telegram message to the specified user.

**Independent test**: Call `GET /api/v1/tgMessage/6696169593?stock=0050` → 200 response, Telegram message received by user 6696169593.

- [ ] T006 [US2] Create `src/fastapistock/services/telegram_service.py` with `send_stock_message(user_id: str, stocks: list[StockData]) -> bool` using `httpx` with `timeout=10`
- [ ] T007 [US2] Create `src/fastapistock/routers/telegram.py` with `GET /api/v1/tgMessage/{id}?stock={codes}` — filter non-numeric codes, call `get_stocks()`, call `send_stock_message()`, skip send if no valid data
- [ ] T008 [US2] Register telegram router in `src/fastapistock/main.py` via `application.include_router(telegram.router)`

---

## Phase 4: Polish

- [ ] T009 [P] Run `uv run ruff check . --fix && uv run ruff format .` and fix any issues
- [ ] T010 [P] Run `uv run mypy src/` and fix any type errors

---

## Dependencies

```
T001 → T002 → T005 (US1 complete)
T001 → T006 → T007 → T008 (US2 complete)
T003 → T006
T004 → T006
```

## MVP Scope

US1 (T001–T005) + US2 (T006–T008) — both are required by the task spec.
