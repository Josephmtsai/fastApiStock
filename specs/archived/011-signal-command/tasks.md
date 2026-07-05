# `/signal` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Telegram `/signal` command that renders all TW and US holdings' long-term add-on signal status without amount advice.

**Architecture:** Implement a focused `signal_service` that fetches existing holdings, reuses existing rich stock services, evaluates status, reads 90-day Redis signal history, and returns MarkdownV2 text. Wire the service into the existing Telegram webhook command dispatcher.

**Tech Stack:** Python 3.11, FastAPI webhook router, Pydantic models, dataclasses, Redis-backed signal history, pytest, Ruff, mypy.

---

## File Structure

- Create `src/fastapistock/services/signal_service.py`
  - Owns `/signal` domain evaluation and MarkdownV2 rendering.
  - Depends on existing portfolio, stock, US stock, and signal history services.
- Modify `src/fastapistock/routers/webhook.py`
  - Adds `/signal` command routing and help text.
- Test `tests/test_signal_service.py`
  - Covers classification, history summary, missing data, and full output.
- Modify `tests/test_webhook.py`
  - Covers webhook dispatch for `/signal`.

## Task 1: Signal Service Classification

**Files:**
- Create: `src/fastapistock/services/signal_service.py`
- Test: `tests/test_signal_service.py`

- [ ] **Step 1: Write failing classification tests**

Add `tests/test_signal_service.py` with tests for TW/US thresholds, observation,
not-add, and data-insufficient cases. Use local helper data; do not call external
services.

Expected test cases:

- TW `price=69`, `week52_high=100`, `ma50=90` -> `深度加碼`
- TW `price=74`, `week52_high=100`, `ma50=90` -> `中度加碼`
- TW `price=80`, `week52_high=100`, `ma50=90` -> `輕度加碼`
- US `price=59`, `week52_high=100`, `ma50=90` -> `深度加碼`
- `price=84`, `week52_high=100`, `ma50=90` -> `觀察`
- `price=90`, `week52_high=100`, `ma50=80` -> `不加碼`
- `week52_high=None` or `ma50=None` -> `資料不足`

- [ ] **Step 2: Run focused failing tests**

Run:

```powershell
$env:UV_CACHE_DIR='D:\claude\fastApiStock\.uv-cache'; uv run pytest tests/test_signal_service.py -q
```

Expected: fail because `signal_service.py` does not exist.

- [ ] **Step 3: Implement minimal classification model**

Create `SignalStatus` dataclass and pure function:

```python
def evaluate_signal_status(
    *,
    symbol: str,
    market: Literal['TW', 'US'],
    price: float | None,
    week52_high: float | None,
    ma50: float | None,
    history_count_90d: int,
) -> SignalStatus:
    ...
```

Implementation rules:

- Use TW thresholds `-30/-25/-20`.
- Use US thresholds `-40/-30/-20`.
- Add-on status requires `price < ma50`.
- `觀察` when no add-on status and either `price < ma50` or `-20 < drop_pct <= -15`.
- `資料不足` when price, week52 high, or MA50 is missing/invalid.
- History label:
  - `0` -> `未觸發`
  - `1` -> `短期訊號`
  - `>=2` -> `訊號持續`

- [ ] **Step 4: Verify classification tests pass**

Run:

```powershell
$env:UV_CACHE_DIR='D:\claude\fastApiStock\.uv-cache'; uv run pytest tests/test_signal_service.py -q
```

Expected: all classification tests pass.

## Task 2: Signal Overview Fetching and Rendering

**Files:**
- Modify: `src/fastapistock/services/signal_service.py`
- Test: `tests/test_signal_service.py`

- [ ] **Step 1: Add failing overview tests**

Add tests that patch:

- `portfolio_repo.fetch_portfolio`
- `portfolio_repo.fetch_portfolio_us`
- `stock_service.get_rich_tw_stocks`
- `us_stock_service.get_us_stocks`
- `signal_history_repo.list_signals`

Test expectations:

- Output contains `加碼訊號總覽`.
- Output contains `台股` and `美股` sections.
- Output includes all patched TW and US holdings.
- Output includes current price, drawdown percent, MA50 state, reason, and 90-day history.
- Output does not contain amount advice keywords: `建議金額`, `買進股數`, `預算`, `剩餘`, `賣出`.

- [ ] **Step 2: Run failing overview tests**

Run:

```powershell
$env:UV_CACHE_DIR='D:\claude\fastApiStock\.uv-cache'; uv run pytest tests/test_signal_service.py -q
```

Expected: fail because `build_signal_overview()` is missing.

- [ ] **Step 3: Implement `build_signal_overview()`**

Add public function:

```python
def build_signal_overview(now: datetime) -> str:
    """Build the MarkdownV2 `/signal` reply for all TW and US holdings."""
```

Required behavior:

- Compute `start_date = now.date() - timedelta(days=90)`.
- Fetch history once with `signal_history_repo.list_signals(start_date, now.date())`.
- Count history by `(market, symbol)`.
- Fetch TW holdings and US holdings from portfolio repo.
- Fetch rich snapshots for holding symbols using existing stock services.
- Render one section per market.
- If a market has no holdings, render `目前無持股資料`.
- If a market fetch fails, render `資料讀取失敗` for that market and continue.

- [ ] **Step 4: Ensure MarkdownV2 escaping**

Use `telegram_service._escape_md()` for dynamic plain text. Numeric code spans
may be used for prices and percentages if consistent with existing formatter.
The final output must be safe for `parse_mode='MarkdownV2'`.

- [ ] **Step 5: Verify overview tests pass**

Run:

```powershell
$env:UV_CACHE_DIR='D:\claude\fastApiStock\.uv-cache'; uv run pytest tests/test_signal_service.py -q
```

Expected: pass.

## Task 3: Webhook `/signal` Dispatch

**Files:**
- Modify: `src/fastapistock/routers/webhook.py`
- Test: `tests/test_webhook.py`

- [ ] **Step 1: Write failing webhook dispatch test**

Add a test that posts an authorized Telegram message containing `/signal`.
Patch `fastapistock.routers.webhook.build_signal_overview` or the imported
service function to return a MarkdownV2 string. Assert:

- Response status is `200`.
- `reply_to_chat()` is called once.
- `parse_mode='MarkdownV2'`.
- Reply text is the service return value.

- [ ] **Step 2: Run failing webhook test**

Run:

```powershell
$env:UV_CACHE_DIR='D:\claude\fastApiStock\.uv-cache'; uv run pytest tests/test_webhook.py -q
```

Expected: fail because `/signal` is not dispatched.

- [ ] **Step 3: Wire command**

Modify `src/fastapistock/routers/webhook.py`:

- Import `build_signal_overview`.
- Add `/signal — 全部持股加碼訊號` to `_HELP_TEXT`.
- Add branch in `_dispatch_message()`:
  - `elif cmd == '/signal':`
  - call `build_signal_overview(datetime.now(ZoneInfo('Asia/Taipei')))`.
  - call `reply_to_chat(chat_id, reply, parse_mode='MarkdownV2')`.
  - return.

- [ ] **Step 4: Verify webhook tests pass**

Run:

```powershell
$env:UV_CACHE_DIR='D:\claude\fastApiStock\.uv-cache'; uv run pytest tests/test_webhook.py -q
```

Expected: pass.

## Task 4: Regression Coverage

**Files:**
- Test: `tests/test_telegram_formatter.py`
- Test: `tests/test_signal_service.py`
- Test: `tests/test_webhook.py`

- [ ] **Step 1: Verify scheduled push formatter behavior is unchanged**

Run:

```powershell
$env:UV_CACHE_DIR='D:\claude\fastApiStock\.uv-cache'; uv run pytest tests/test_telegram_formatter.py -q
```

Expected: pass. This confirms existing scheduled rich stock add-on signal output
still behaves as before.

- [ ] **Step 2: Verify focused `/signal` tests**

Run:

```powershell
$env:UV_CACHE_DIR='D:\claude\fastApiStock\.uv-cache'; uv run pytest tests/test_signal_service.py tests/test_webhook.py -q
```

Expected: pass.

- [ ] **Step 3: Run project quality gates**

Run:

```powershell
$env:UV_CACHE_DIR='D:\claude\fastApiStock\.uv-cache'; uv run ruff check . --fix
$env:UV_CACHE_DIR='D:\claude\fastApiStock\.uv-cache'; uv run ruff format .
$env:UV_CACHE_DIR='D:\claude\fastApiStock\.uv-cache'; uv run mypy src/
$env:UV_CACHE_DIR='D:\claude\fastApiStock\.uv-cache'; uv run pytest -q
```

Expected: all pass.

## Acceptance Criteria Mapping

| AC | Tasks |
| --- | --- |
| AC1 | Task 3 |
| AC2 | Task 2 |
| AC3 | Task 1 |
| AC4 | Task 1 |
| AC5 | Task 1 |
| AC6 | Task 1, Task 2 |
| AC7 | Task 1, Task 2 |
| AC8 | Task 2 |
| AC9 | Task 2 |
| AC10 | Task 4 |

## Self-Review

- Spec coverage: every acceptance criterion maps to at least one task.
- Marker scan: no unfinished marker text remains.
- Scope check: v1 is one Telegram command and one service module; no dashboard,
  public API, ranking, budget, or portfolio-weight subsystem is included.
