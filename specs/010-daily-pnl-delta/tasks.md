# Daily PnL Delta Implementation Plan

**Goal:** Add scheduled market-specific PnL comparison versus each market's own
previous-close baseline.

**Architecture:** Reuse existing Google Sheets PnL readers and Redis snapshot
patterns. Add daily market-close snapshots, calculate one-market deltas in
`portfolio_service`, and wire the scheduler so TW quote pushes send TW-only PnL
delta messages and US quote pushes send US-only PnL delta messages.

**Tech Stack:** Python 3.11, FastAPI, APScheduler, Redis cache wrapper, pytest,
Ruff, mypy.

---

## File Map

- Modify `src/fastapistock/repositories/portfolio_snapshot_repo.py`
  - Add `save_daily()` / `get_daily()` helpers keyed by market and trading date.
- Modify `src/fastapistock/services/portfolio_service.py`
  - Add pure market-specific PnL delta formatter.
  - Add close snapshot capture and read-side reply helpers.
- Modify `src/fastapistock/scheduler.py`
  - Add TW and US close-baseline jobs.
  - Send TW/US PnL delta messages only for the active market after quote pushes.
- Modify `src/fastapistock/services/telegram_service.py`
  - Add a narrow plain-text send helper if the rich quote sender cannot append
    custom content safely.
- Modify `tests/test_portfolio_snapshot_repo.py`.
- Modify `tests/test_portfolio_service.py`.
- Modify `tests/test_scheduler.py`.

## Task 1 - Daily Snapshot Repository

**Files:**

- Modify: `src/fastapistock/repositories/portfolio_snapshot_repo.py`
- Test: `tests/test_portfolio_snapshot_repo.py`

- [x] Add tests for TW and US daily snapshot save/get round trips.
- [x] Add `_DAILY_PREFIX = 'portfolio:snapshot:daily'`.
- [x] Add `save_daily(market, trading_date, snapshot)`.
- [x] Add `get_daily(market, trading_date)`.
- [x] Validate market codes as `TW` or `US`.
- [x] Preserve graceful handling of malformed Redis values.

## Task 2 - Market-Specific PnL Delta Formatting

**Files:**

- Modify: `src/fastapistock/services/portfolio_service.py`
- Test: `tests/test_portfolio_service.py`

- [x] Add failing tests for complete US delta formatting:
  - Header: `US PnL vs previous close`
  - `Current: +350,000 TWD`
  - `Previous close: +320,000 TWD`
  - `Change: +30,000 TWD`
- [x] Add missing-baseline tests:
  - `No US previous-close baseline yet.`
  - `Current: +350,000 TWD`
  - No `Current total`.
- [x] Add current-unavailable regression tests:
  - `US current PnL unavailable.`
  - No synthetic `+0 TWD`.
- [x] Add TW-only output regression tests:
  - TW output must not contain `US:` or `Total:`.
- [x] Implement `format_market_daily_pnl_delta(market, current_pnl, previous_pnl)`.

## Task 3 - Baseline Capture And Reply Helpers

**Files:**

- Modify: `src/fastapistock/services/portfolio_service.py`
- Test: `tests/test_portfolio_service.py`

- [x] Implement `save_daily_close_snapshot(market, trading_date, captured_at)`.
- [x] TW snapshot captures only `fetch_pnl_tw()`.
- [x] US snapshot captures only `fetch_pnl_us()`.
- [x] Return `False` when the current market PnL is unavailable.
- [x] Implement `get_daily_pnl_delta_reply(market, trading_date)`.
- [x] Read only the requested market's daily baseline.
- [x] Format only the requested market's PnL delta.

## Task 4 - Scheduler Close Snapshot Jobs

**Files:**

- Modify: `src/fastapistock/scheduler.py`
- Test: `tests/test_scheduler.py`

- [x] Add `capture_tw_close_snapshot()`.
- [x] Add `capture_us_close_snapshot()`.
- [x] TW close snapshot stores the current Asia/Taipei date.
- [x] US close snapshot at Taiwan early morning stores the previous calendar date
  as the US trading date.
- [x] Add APScheduler jobs:
  - `tw_daily_close_snapshot`: Monday-Friday 14:10 Asia/Taipei.
  - `us_daily_close_snapshot`: Tuesday-Saturday 04:10 Asia/Taipei.

## Task 5 - Scheduled Push Delta Message

**Files:**

- Modify: `src/fastapistock/scheduler.py`
- Modify: `src/fastapistock/services/telegram_service.py`
- Test: `tests/test_scheduler.py`

- [x] Add `_previous_tw_trading_date()` and `_previous_us_trading_date()` helpers.
- [x] Skip weekends for previous-close lookup.
- [x] Add `_send_daily_pnl_delta(market, now=None)`.
- [x] TW scheduled pushes call `_safe_send_daily_pnl_delta('TW')`.
- [x] US scheduled pushes call `_safe_send_daily_pnl_delta('US')`.
- [x] Keep quote pushes isolated from PnL delta failures.
- [x] Add `send_text_message(user_id, text)` with Telegram HTTP timeout.

## Task 6 - Validation

- [x] Focused market-specific tests:

```powershell
uv run pytest tests/test_portfolio_service.py::TestDailyPnlDelta tests/test_scheduler.py::TestScheduledPush -q
```

- [x] Related regression tests:

```powershell
uv run pytest tests/test_portfolio_snapshot_repo.py tests/test_portfolio_service.py tests/test_scheduler.py -q
```

- [x] Ruff check:

```powershell
uv run ruff check . --fix
```

- [x] Mypy:

```powershell
uv run mypy src/
```

- [ ] Ruff format:

```powershell
uv run ruff format .
```

- [ ] Full test suite:

```powershell
uv run pytest -q
```

- [ ] Pre-commit:

```powershell
uv run pre-commit run --all-files
```

## Acceptance Criteria Mapping

- US1: Tasks 2, 3, and 5.
- US2: Tasks 1, 3, and 4.
- US3: Tasks 2, 3, and 5.

## Definition of Done

- Daily TW/US close snapshots are stored separately in Redis.
- US close snapshot uses the previous US trading date when captured in Taiwan
  early morning.
- Scheduled quote pushes continue when PnL comparison fails.
- TW push compares only TW current PnL against TW previous close.
- US push compares only US current PnL against US previous close.
- Cross-market total PnL is not displayed in scheduled delta messages.
- Focused tests, Ruff, mypy, and QA validation pass.
