# 010 Daily PnL Delta Against Market Close Baselines

## Overview

Add a daily portfolio PnL comparison to the existing scheduled quote push.
The feature compares only total unrealized PnL, not per-symbol PnL.

TW and US portfolios must use separate market-close baselines:

- TW baseline: the TW portfolio total PnL captured after Taiwan market close.
- US baseline: the US portfolio total PnL captured after US market close.

Every 30-minute quote push may include a compact PnL delta section for the
active market only. TW pushes compare TW current PnL against the TW previous
close baseline. US pushes compare US current PnL against the US previous close
baseline. Cross-market totals are no longer displayed.

## User Stories

### US1 - See total PnL movement during quote pushes

As an investor, I want each scheduled quote push to include that market's PnL
movement versus yesterday's market-close baseline, so that I can quickly know
whether the active market's portfolio is better or worse than the previous close.

Acceptance Criteria:

- Given both TW and US close baselines exist
- When a scheduled push runs during either market window
- Then a TW push includes only TW current PnL, TW previous-close baseline, and
  TW delta
- Then a US push includes only US current PnL, US previous-close baseline, and
  US delta

### US2 - Keep TW and US baselines aligned to their own markets

As an investor, I want TW and US baselines captured after each market closes, so
that the comparison does not mix Taiwan daytime data with US overnight data.

Acceptance Criteria:

- Given a TW market day after TW close
- When the TW close snapshot job runs
- Then it stores `portfolio:snapshot:daily:tw:{YYYY-MM-DD}` for the TW trading
  date
- Given a US market day after US close in Asia/Taipei time
- When the US close snapshot job runs
- Then it stores `portfolio:snapshot:daily:us:{YYYY-MM-DD}` for the US trading
  date, not the Asia/Taipei calendar date

### US3 - Degrade gracefully when a baseline or PnL source is unavailable

As an investor, I want the bot to keep sending quote messages even when PnL data
or baselines are unavailable, so that quote delivery is not blocked.

Acceptance Criteria:

- Given current PnL cannot be fetched
- When a scheduled push runs
- Then the existing quote message is still sent and the PnL delta section says
  current PnL is unavailable
- Given a prior close baseline is missing
- When a scheduled push runs
- Then the PnL delta section says no previous-close baseline exists yet

## Modules

### Existing Modules To Extend

| Module | Change |
| --- | --- |
| `src/fastapistock/repositories/portfolio_snapshot_repo.py` | Add daily TW/US snapshot save/get helpers. |
| `src/fastapistock/services/portfolio_service.py` | Add pure PnL delta calculation and formatting helpers. |
| `src/fastapistock/scheduler.py` | Add TW/US close snapshot jobs and include PnL delta text in scheduled pushes. |
| `tests/test_portfolio_snapshot_repo.py` | Add daily snapshot tests. |
| `tests/test_portfolio_service.py` | Add delta calculation and formatting tests. |
| `tests/test_scheduler.py` | Add market-close scheduler job tests. |

### New Concepts

`DailyPnlSnapshot`

- Market: `TW` or `US`
- Trading date: ISO date for the market session being captured
- PnL total: one market's total unrealized PnL in TWD
- Captured timestamp: Asia/Taipei aware datetime

`MarketDailyPnlDelta`

- Market: `TW` or `US`
- Current market PnL
- Market previous-close baseline
- Market delta

## Data Contracts

Redis keys:

```text
portfolio:snapshot:daily:tw:{YYYY-MM-DD}
portfolio:snapshot:daily:us:{YYYY-MM-DD}
```

Value shape:

```json
{
  "market": "TW",
  "trading_date": "2026-05-19",
  "pnl": "123456.0",
  "timestamp": "2026-05-19T14:10:00+08:00"
}
```

Notes:

- `pnl` should be stored as a string or numeric value that can be parsed back
  to float.
- The repository must tolerate existing malformed Redis values and return
  `None` rather than raising.
- TTL may reuse the existing snapshot TTL of 120 days unless implementation
  identifies a stronger existing project convention.

## Scheduler Design

Add two close-baseline jobs:

- TW close snapshot: Asia/Taipei, Monday-Friday, around `14:10`.
- US close snapshot: Asia/Taipei, Tuesday-Saturday, around `04:10`.

Trading-date mapping:

- TW snapshot trading date is `now.date()` in Asia/Taipei.
- US snapshot trading date is `(now.date() - 1 day)` because US close occurs
  around Taiwan early morning for the prior US market date.

Scheduled push behavior:

- Keep the existing 30-minute quote push.
- After TW quotes are fetched, build a TW-only PnL delta text block through
  `portfolio_service`.
- After US quotes are fetched, build a US-only PnL delta text block through
  `portfolio_service`.
- Append the PnL delta block to the Telegram message where the existing
  message-sending API supports it.
- If the existing rich Telegram sender cannot append custom sections cleanly,
  send a second compact PnL delta message after the quote message. Prefer the
  second message over invasive changes to stock quote rendering.

## Telegram Output

Target plain-text content:

```text
US PnL vs previous close

Current: +350,000 TWD
Previous close: +320,000 TWD
Change: +30,000 TWD
```

Missing baseline:

```text
US PnL vs previous close

No US previous-close baseline yet.
Current: +350,000 TWD
```

Partial data:

```text
US PnL vs previous close

US current PnL unavailable.
```

Chinese copy can be adjusted during implementation to match existing bot
messages. The behavior and fields above are the contract.

## External Data Sources

- Current TW PnL for TW messages: `portfolio_repo.fetch_pnl_tw()`
- Current US PnL for US messages: `portfolio_repo.fetch_pnl_us()`
- Existing functions read Google Sheets CSV with HTTP timeout and Redis cache.

No new external stock-price API is needed for this feature.

## Security / Rate Limiting

- No new public API route is required.
- Existing Telegram webhook/API rate limiting is unchanged.
- Scheduled jobs must log failures and return without raising so APScheduler
  continues running.

## Cache / Timeout / Random Sleep

- Google Sheets reads already use `httpx.get(..., timeout=10)`.
- PnL fetches already use Redis cache keys scoped by date.
- No new TWSE/yfinance quote fetch is required, so no new random sleep is
  required for this feature.

## Edge Cases

| Case | Expected behavior |
| --- | --- |
| TW current PnL unavailable | Do not save TW close snapshot; push message marks TW unavailable. |
| US current PnL unavailable | Do not save US close snapshot; push message marks US unavailable. |
| Redis read/write fails | Log warning; continue quote push. |
| First day after deployment | Show no previous-close baseline yet. |
| Weekend / holiday | Snapshot jobs may run on weekday schedule, but save only when PnL is available. No holiday calendar is required for MVP. |
| US date crossover | US 04:10 Asia/Taipei snapshot stores previous calendar date as trading date. |
| Baseline is zero | Currency delta works; percentage delta is out of scope. |

## Out of Scope

- Per-symbol PnL comparison.
- Cross-market total PnL display.
- Percentage change display.
- New database tables or Alembic migration.
- Modifying `/pnl` command output.
- Holiday calendar integration.
- Recalculating PnL from current market prices.
