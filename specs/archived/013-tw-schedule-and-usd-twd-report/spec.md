# Spec — Feature 013: TW Schedule Adjustment + USD→TWD Daily Report

## Overview

調整台股報價推播的時間窗口起始時間（08:30 → 09:30 GMT+8），並在每日損益報告的「美股今日」欄位附加 USD→TWD 換算金額。

---

## User Stories

### US-1: 台股推播時間調整

As a 投資人,
I want the Taiwan stock quote push to start no earlier than 09:30 Asia/Taipei,
so that I do not receive pre-open noise before the market officially opens.

**Acceptance Criteria**

- Given the scheduler fires at 09:29 Asia/Taipei on a weekday
- When `is_tw_market_window()` is evaluated
- Then it returns `False`

- Given the scheduler fires at 09:30 Asia/Taipei on a weekday
- When `is_tw_market_window()` is evaluated
- Then it returns `True`

- Given the scheduler fires at 14:00 Asia/Taipei on a weekday
- When `is_tw_market_window()` is evaluated
- Then it returns `True` (end time unchanged)

- Given the scheduler fires at 14:01 Asia/Taipei on a weekday
- When `is_tw_market_window()` is evaluated
- Then it returns `False`

- Given it is Saturday or Sunday
- When `is_tw_market_window()` is evaluated at any time
- Then it returns `False`

- Given the US market window logic exists independently
- When the TW window boundary is changed
- Then `is_us_market_window()` is not affected


### US-2: 每日損益報告附加美股台幣換算

As a 投資人,
I want to see the US stock daily P&L converted to TWD in the daily report,
so that I can compare US and TW performance in the same currency at a glance.

**Acceptance Criteria**

- Given the USD/TWD rate is successfully fetched (e.g. 32.50)
  and us_today = +1,257.93 USD
- When `build_pnl_report()` is called
- Then the 美股今日 line reads:
  `🇺🇸 美股今日：+US$1,257.93 (≈NT$40,883) ｜ 持倉：...`
  (TWD figure is `round(us_today * rate, 0)`, formatted as integer with comma)

- Given the USD/TWD rate fetch fails (network error or timeout)
- When `build_pnl_report()` is called
- Then the 美股今日 line falls back to original format without TWD suffix
  and the report is still sent (no exception propagation)

- Given us_today is `None` (US portfolio fetch failed)
- When `build_pnl_report()` is called
- Then the line reads `🇺🇸 美股：資料讀取失敗` (existing behaviour unchanged)

- Given the USD/TWD rate is stale (same calendar day)
- When `fx_service.get_usd_twd_rate()` is called a second time within TTL
- Then Redis cache is hit and no yfinance call is made

---

## Modules

| Module | 職責 | 涉及檔案 |
|--------|------|---------|
| `scheduler.is_tw_market_window` | 台股時間窗判斷，調整 lower bound 從 08:30 → 09:30 | `src/fastapistock/scheduler.py` |
| `fx_service` | 新模組：提供 `get_usd_twd_rate() -> float \| None`，Redis cache + yfinance fallback | `src/fastapistock/services/fx_service.py` |
| `pnl_service._fmt_us_today_line` | 組裝美股今日行，根據是否有匯率選擇顯示格式 | `src/fastapistock/services/pnl_service.py` |
| `config` | 新增 `FX_CACHE_TTL` 常數（env var，預設 14400 秒 = 4 小時） | `src/fastapistock/config.py` |
| `test_scheduler` | 更新既有 boundary tests（08:29/08:30 → 09:29/09:30） | `tests/test_scheduler.py` |
| `test_fx_service` | 新增單元測試 | `tests/test_fx_service.py` |
| `test_pnl_service` | 新增 TWD conversion 測試案例 | `tests/test_pnl_service.py` |

---

## Data Contracts

### fx_service

```python
# src/fastapistock/services/fx_service.py

_FX_CACHE_KEY = 'fx:usd_twd:{date}'  # e.g. 'fx:usd_twd:2026-06-13'

def get_usd_twd_rate() -> float | None:
    """Return today's USD/TWD spot rate, Redis-cached.

    Returns:
        Rate as float (e.g. 32.50), or None if unavailable.
    """
```

**Cache entry schema** (stored in Redis via `redis_cache.put`):

```python
{"rate": float}   # e.g. {"rate": 32.5}
```

**yfinance call spec**:
- Ticker: `TWD=X`
- `period='1d'`
- `timeout`: read from env `YFINANCE_TIMEOUT` (default 10 seconds)
- Random sleep: `random.uniform(0.1, 0.4)` before live fetch (per CLAUDE.md)
- On any exception or empty result: return `None` (no raise)

### pnl_service changes

```python
# New helper (internal)
def _fmt_us_today_line(us_today: float, rate: float | None) -> str:
    """Build the 美股今日 line with optional TWD annotation.

    Args:
        us_today: US daily P&L in USD.
        rate: USD/TWD rate, or None if unavailable.

    Returns:
        MarkdownV2-escaped line string.
    """
```

Display format when rate is available:
```
🇺🇸 美股今日：+US$1,257.93 (≈NT$40,883) ｜ 持倉：+US$54,560.84
```

- TWD amount = `round(us_today * rate)` → formatted as integer with comma, sign prefix
- If `us_today` is negative: `≈NT$-xx,xxx`
- TWD parenthetical is inserted between USD amount and `｜ 持倉` (or end of line if no holdings)

Display format when rate is `None` (fallback):
```
🇺🇸 美股今日：+US$1,257.93 ｜ 持倉：+US$54,560.84
```

---

## API Design

No new HTTP routes. This feature is purely internal (scheduler + service layer).

---

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `FX_CACHE_TTL` | `14400` | Redis TTL for USD/TWD rate, in seconds (4 hours) |
| `YFINANCE_TIMEOUT` | `10` | HTTP timeout for yfinance FX fetch, in seconds |

Both are optional. `config.py` reads them via `os.getenv()`.

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| yfinance returns empty DataFrame | Return `None`; report falls back to USD-only |
| yfinance raises `Exception` | Caught, logged as warning, return `None` |
| Redis unavailable during FX cache write | `redis_cache.put()` already swallows `RedisError`; no impact |
| Redis unavailable during FX cache read | `redis_cache.get()` returns `None`; fall through to yfinance |
| `us_today = 0.0` | TWD = `≈NT$0`; sign prefix `+` (matches existing `_fmt_us_amount` convention) |
| Rate fetch succeeds but `us_today` is `None` | `us_today is None` path handled before rate is used; no change |
| Weekend / holiday (no yfinance data for today) | `period='1d'` may return last trading day Close; acceptable |
| `is_tw_market_window` boundary 09:29 | Returns `False` |
| `is_tw_market_window` boundary 09:30 | Returns `True` |
| Existing TW window end 14:00 | Unchanged, returns `True` |
| Existing US window | Unchanged by this feature |

---

## Impact Analysis (既有功能影響)

| 元件 | 影響 | 說明 |
|------|------|------|
| `push_tw_stocks` | 間接影響：推播觸發時間延後 1 小時 | 09:00 tick 不再推送，09:30 tick 開始推送 |
| `_safe_send_daily_pnl_delta('TW')` | 同 `push_tw_stocks`，09:30 才開始推 | 無邏輯變更，僅時間窗口改變 |
| `push_us_stocks` | 不影響 | `is_us_market_window` 未更動 |
| `build_pnl_report` | 新增 `get_usd_twd_rate()` 呼叫 | 失敗 fallback 保護既有格式，不破壞現有輸出 |
| TW close snapshot (14:10) | 不影響 | 獨立 CronTrigger，不依賴 `is_tw_market_window` |
| US close snapshot (04:10) | 不影響 | 同上 |
| `TestTwMarketWindow` (8 tests) | 需更新 2 個邊界測試 | `test_window_start_0830_monday_is_in` → 09:30，`test_before_window_0829_monday_is_out` → 09:29 |

---

## Out of Scope

- 持倉損益（`持倉：+US$xx,xxx`）不換算台幣（僅今日損益換算）
- 台股的 TWD 欄位不受影響
- FX rate 的歷史查詢或月報功能（由 `backfill_history.py` 處理）
- 市場休市日（holiday）辨識
- 匯率數值精度超過兩位小數
