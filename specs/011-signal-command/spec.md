# Spec 011 - Telegram `/signal` Add-On Signal Overview

**Date**: 2026-05-21
**Role**: fastapistock-sa
**Status**: Ready for implementation planning

---

## Overview

Add a Telegram `/signal` command that shows add-on signal status for all current
TW and US holdings. The command is for long-term manual add-on decisions. It
must not recommend amounts, shares, priority ranking, or sell actions.

The first version is intentionally lightweight:

- Manual command only: `/signal`
- Scope: all current TW and US holdings
- Signal basis: current price, 52-week high drawdown, MA50 condition, and
  existing 90-day signal history
- No budget, cash, target allocation, or overweight checks
- Scheduled stock push behavior remains unchanged

## User Stories

### US1 - View all holding signal states

As a long-term investor, I want `/signal` to show every current holding's
add-on signal status, so that I can manually decide whether any holding deserves
attention.

### US2 - See why a holding is not actionable

As a long-term investor, I want each non-triggered holding to include a concise
reason, so that I can distinguish "not enough drawdown", "MA50 not broken", and
"data unavailable".

### US3 - See recent signal persistence

As a long-term investor, I want each holding to show 90-day signal history, so
that I can tell whether the signal is persistent or just a one-off event.

## Acceptance Criteria

### AC1 - `/signal` dispatch

Given an authorized Telegram user sends `/signal`
When the webhook receives the message
Then the bot replies with a MarkdownV2-formatted add-on signal overview.

### AC2 - All holdings included

Given TW and US portfolio entries exist
When `/signal` is executed
Then the reply includes both TW and US sections and includes every holding that
can be read from the portfolio source.

### AC3 - Status classification

Given a holding has current price, week52 high, and MA50
When `/signal` evaluates that holding
Then the status is one of:

- `深度加碼`
- `中度加碼`
- `輕度加碼`
- `觀察`
- `不加碼`
- `資料不足`

### AC4 - Add-on thresholds reuse existing behavior

Given a holding satisfies existing add-on signal thresholds
When `/signal` evaluates it
Then TW thresholds remain `-20% / -25% / -30%` and US thresholds remain
`-20% / -30% / -40%`.

### AC5 - Observation rule

Given a holding does not satisfy an add-on threshold
When the holding either has price below MA50 or drawdown is between `-15%` and
`-20%`
Then `/signal` classifies it as `觀察`.

### AC6 - Not-add reason

Given a holding has complete data but neither add-on nor observation conditions
are met
When `/signal` renders the row
Then it shows `不加碼` and includes the main reason, such as `回檔未達門檻` or
`MA50 條件未成立`.

### AC7 - Data insufficient reason

Given current price, week52 high, or MA50 is missing or invalid
When `/signal` evaluates the holding
Then it shows `資料不足` and states which field is missing.

### AC8 - 90-day history

Given signal history records exist in Redis for the last 90 days
When `/signal` renders the holding
Then it shows the number of records for that symbol and a concise persistence
label:

- `未觸發` for zero records
- `短期訊號` for one record
- `訊號持續` for two or more records

### AC9 - No amount advice

Given `/signal` output is generated
When the user reads the reply
Then it must not contain suggested investment amount, share count, cash budget,
remaining budget, ranking, or sell guidance.

### AC10 - Existing scheduled push unchanged

Given scheduled TW/US push runs
When a stock does or does not trigger add-on signal
Then the existing stock message behavior remains unchanged and `/signal` logic
does not add full all-holding status to scheduled push.

## Modules

### New service module

`src/fastapistock/services/signal_service.py`

Responsibilities:

- Fetch current TW and US holdings.
- Fetch rich stock snapshots for all holdings using existing service functions.
- Evaluate current signal status without persisting new signal history.
- Fetch 90-day history through `signal_history_repo.list_signals()`.
- Format a MarkdownV2 Telegram reply for `/signal`.

The service should keep domain computation separate from text rendering:

- `SignalStatus`: dataclass representing one holding's evaluation.
- `build_signal_overview(now: datetime) -> str`: public entry point for webhook.

### Existing modules to modify

`src/fastapistock/routers/webhook.py`

- Add `/signal` to `_HELP_TEXT`.
- Add `/signal` branch in `_dispatch_message()`.
- Reply using `parse_mode='MarkdownV2'`.

`src/fastapistock/services/telegram_service.py`

- Reuse `_escape_md()` for MarkdownV2 output.
- Refactor signal threshold calculation only if needed to avoid duplicating
  threshold logic. Do not change scheduled push behavior.

`src/fastapistock/services/stock_service.py`

- Reuse `get_rich_tw_stocks()` for TW holding symbols.
- Do not introduce new external TW fetch path.

`src/fastapistock/services/us_stock_service.py`

- Reuse `get_us_stocks()` for US holding symbols.
- Continue respecting existing US cache behavior.

`src/fastapistock/repositories/portfolio_repo.py`

- Reuse `fetch_portfolio()` and `fetch_portfolio_us()`.
- No schema change required.

`src/fastapistock/repositories/signal_history_repo.py`

- Reuse `list_signals(start_date, end_date)`.
- No Redis key change required.

## Data Contracts

### SignalStatus

Fields:

- `symbol: str`
- `market: Literal['TW', 'US']`
- `status: Literal['深度加碼', '中度加碼', '輕度加碼', '觀察', '不加碼', '資料不足']`
- `price: float | None`
- `drop_pct: float | None`
- `ma50: float | None`
- `ma50_broken: bool | None`
- `reason: str`
- `history_count_90d: int`
- `history_label: Literal['未觸發', '短期訊號', '訊號持續']`

### Thresholds

TW:

- `drop_pct <= -30`: `深度加碼`
- `drop_pct <= -25`: `中度加碼`
- `drop_pct <= -20`: `輕度加碼`

US:

- `drop_pct <= -40`: `深度加碼`
- `drop_pct <= -30`: `中度加碼`
- `drop_pct <= -20`: `輕度加碼`

All add-on statuses additionally require `price < ma50`.

### Observation

`觀察` applies when no add-on status matched and either:

- `price < ma50`, or
- `-20 < drop_pct <= -15`

## Telegram Flow

### Command

`/signal`

No arguments are supported in v1. Extra arguments are ignored or produce the same
full overview; implementation should choose the simpler behavior and document it
in tests.

### Example Output

```text
📌 加碼訊號總覽

🇹🇼 台股
2330：深度加碼
現價 820.00 | 距高點 -31.2% | MA50 已跌破
原因：回檔達深度門檻，趨勢條件成立
近 90 天：觸發 4 次，訊號持續

0050：觀察
現價 182.00 | 距高點 -16.8% | MA50 已跌破
原因：趨勢條件成立，但回檔未達加碼門檻
近 90 天：未觸發

🇺🇸 美股
AAPL：不加碼
現價 190.20 | 距高點 -24.1% | MA50 未跌破
原因：MA50 條件未成立
近 90 天：觸發 1 次，短期訊號
```

## External Data Sources

- TW holdings: existing Google Sheets portfolio source through
  `portfolio_repo.fetch_portfolio()`
- US holdings: existing Google Sheets portfolio source through
  `portfolio_repo.fetch_portfolio_us()`
- TW rich prices and indicators: existing `stock_service.get_rich_tw_stocks()`
- US rich prices and indicators: existing `us_stock_service.get_us_stocks()`
- Signal history: Redis via `signal_history_repo.list_signals()`

## Security / Rate Limiting

- `/signal` enters through the existing Telegram webhook route, which already
  validates Telegram secret and authorized user ID.
- It uses the existing webhook rate limit bucket.
- No new public HTTP API endpoint is in scope for v1.

## Cache / Timeout / Random Sleep

- Use existing rich stock service functions so current cache and outbound
  request safeguards remain in effect.
- Do not add a new external request layer.
- Do not call TW or US repositories directly from the webhook.

## Edge Cases

| Case | Expected behavior |
| --- | --- |
| No TW holdings | Show TW section with `目前無持股資料` |
| No US holdings | Show US section with `目前無持股資料` |
| One market fetch fails | Show the failed market as `資料讀取失敗`; still render the other market |
| One symbol rich fetch fails | Mark that symbol as `資料不足` if symbol is known; do not fail entire reply |
| Missing `week52_high` | `資料不足`, reason mentions missing 52-week high |
| Missing `ma50` | `資料不足`, reason mentions missing MA50 |
| Invalid `week52_high <= 0` | `資料不足` |
| No history records | `近 90 天：未觸發` |
| Telegram Markdown special chars | Escape all dynamic text using MarkdownV2 escaping |

## Out of Scope

- Investment amount suggestions
- Share quantity suggestions
- Cash or monthly budget display
- Add-on ranking or priority ordering
- Portfolio concentration or overweight checks
- `tw/us/symbol` filters
- New dashboard or public API endpoint
- Sell, stop-loss, or take-profit recommendations
- Changing scheduled push behavior
