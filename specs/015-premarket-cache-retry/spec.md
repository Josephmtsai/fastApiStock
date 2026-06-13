# Spec — Feature 015: Pre-market Cache + Retry (OpenSpec)

## Overview

在 `_fetch_premarket_price` 的盤前 window 內（Eastern Time 04:00–09:30），對 yfinance 的 1-minute history 呼叫加入最多 3 次指數退避重試（Exponential Backoff Retry）；同時在 `us_stock_service` 的 `_cache_key` 改為以 **小時** 為 TTL 粒度（而非日期），使盤前快取在開盤後自然過期，避免盤前快取價格殘留到盤中。

---

## User Stories

### US-015-1

As a 投資人,
I want the pre-market price fetch to retry up to 3 times with exponential backoff when yfinance returns empty data or raises a network error during 04:00–09:30 ET,
so that transient yfinance rate-limit or timeout errors do not cause the pre-market price to silently show as None in Telegram pushes.

**Acceptance Criteria:**

- Given 目前 ET 時間在 04:00–09:30（盤前 window）
- When `ticker.history(prepost=True, ...)` 首次呼叫回傳空 DataFrame 或拋出 Exception
- Then 系統以 1s、2s、4s 間隔自動重試最多 3 次
- And 若 3 次均失敗，回傳 `None`（不 raise）
- And 每次重試前使用 `time.sleep` 執行退避等待
- And 所有重試次數與失敗原因均以 `logger.warning` 記錄

### US-015-2

As a 投資人,
I want the US stock Redis cache key to include the UTC hour so that pre-market prices cached at 06:00 ET are not served 6 hours later when the regular session has already started,
so that the scheduled Telegram push during market hours always shows fresh regular-session prices.

**Acceptance Criteria:**

- Given `us_stock_service._cache_key` 當前以 `date.today()` 生成 key
- When 快取 key 改為 `us_stock:{symbol}:{date}:{hour_utc}` 格式
- Then 盤前 key（例如 `us_stock:AAPL:2026-06-13:9`）與盤中 key（`us_stock:AAPL:2026-06-13:14`）不同，自然互不命中
- And `US_STOCK_CACHE_TTL` 環境變數語意不變（秒為單位）
- And 既有 `get_us_stock` 與 `get_us_stocks` 呼叫路徑無其他行為變更

### US-015-3

As a 開發者,
I want all new retry logic covered by unit tests using `unittest.mock`,
so that regressions in the retry/backoff path are caught in CI.

**Acceptance Criteria:**

- Given 新增的重試邏輯在 `_fetch_premarket_price`
- When 執行 `uv run pytest tests/test_us_stock_repo.py`
- Then 新增測試覆蓋：(a) 第 1 次失敗、第 2 次成功；(b) 連續 3 次失敗回傳 None；(c) sleep 呼叫次數與退避秒數正確
- And 針對新 cache key 格式新增測試覆蓋：key 包含當前 UTC hour

---

## OpenSpec

```yaml
openspec: "1.0"
feature: "015-premarket-cache-retry"

functions:
  - name: "_fetch_premarket_price"
    module: "fastapistock.repositories.us_stock_repo"
    signature: "(ticker: yf.Ticker) -> float | None"
    behaviour:
      - guard: "ET wall-clock not in [04:00, 09:30) → return None immediately"
      - loop: "attempt in range(0, PREMARKET_MAX_RETRIES + 1)"
      - on_success: "return round(float(last_close), 2)"
      - on_empty_df: "raise ValueError('Empty pre-market history') → triggers retry"
      - on_exception: "log warning(attempt, reason) → sleep(base * 2^attempt) → next attempt"
      - on_exhausted: "return None"
    constraints:
      - "time.sleep is used (sync); no asyncio"
      - "ET window guard remains OUTSIDE the retry loop"
      - "Function body ≤ 50 lines; overflow → extract _attempt_premarket_fetch()"

  - name: "_cache_key"
    module: "fastapistock.services.us_stock_service"
    signature: "(symbol: str) -> str"
    returns: "f'us_stock:{symbol}:{date}:{utc_hour}'"
    example: "'us_stock:AAPL:2026-06-13:14'"
    constraints:
      - "hour is UTC (not ET), consistent with date.today() UTC baseline"
      - "hour is 0-padded: NO — plain int (0–23)"

config:
  new_env_vars:
    PREMARKET_MAX_RETRIES:
      type: int
      default: 3
      description: "Maximum retry attempts for pre-market yfinance calls"
    PREMARKET_RETRY_BASE_SLEEP:
      type: float
      default: 1.0
      description: "Base sleep seconds; doubles each retry (exponential backoff)"

error_handling:
  empty_dataframe: "raise ValueError internally → treated as retryable failure"
  exception: "caught, logged as warning, retry until exhausted"
  exhausted: "return None — caller handles missing pre-market price"
  window_miss: "return None immediately — no retry, no log"

cache_key_migration:
  old_format: "us_stock:{symbol}:{YYYY-MM-DD}"
  new_format: "us_stock:{symbol}:{YYYY-MM-DD}:{H}"
  migration: "old keys expire naturally via US_STOCK_CACHE_TTL; no manual flush needed"
```

---

## Modules

| Module | 職責 | 涉及檔案 |
|--------|------|----------|
| `premarket_retry` | 在 `_fetch_premarket_price` 加入最多 3 次指數退避重試邏輯 | `src/fastapistock/repositories/us_stock_repo.py` |
| `cache_key_hourly` | 將 `_cache_key` 改為 `us_stock:{symbol}:{date}:{hour_utc}` | `src/fastapistock/services/us_stock_service.py` |
| `config_constants` | 新增 `PREMARKET_MAX_RETRIES`、`PREMARKET_RETRY_BASE_SLEEP` | `src/fastapistock/config.py` |
| `tests_repo` | 覆蓋重試分支的單元測試 | `tests/test_us_stock_repo.py` |
| `tests_service` | 覆蓋新 cache key 格式的單元測試 | `tests/test_us_stock_service.py` |

---

## Edge Cases

| 情境 | 期望行為 |
|------|----------|
| 第 1 次空 DataFrame，第 2 次有資料 | 回傳第 2 次結果，共 sleep 1 次（1s） |
| 連續 3 次 Exception | 全部吞掉，回傳 `None`，logger.warning 記錄 3 次 |
| 連續 3 次空 DataFrame | 視同失敗，回傳 `None` |
| ET 時間 ≥ 09:30（window 外） | 不進入重試邏輯，直接回傳 `None`（現有 guard 維持） |
| `PREMARKET_MAX_RETRIES=0`（env 設為 0） | 不重試，行為退化為現有邏輯（只嘗試 1 次） |
| Redis 不可用 | `redis_cache.get` 回傳 `None`，走 miss 路徑，不影響重試邏輯 |
| Cache key 格式變更後，舊格式 key 殘留 Redis | 舊 key 依 `US_STOCK_CACHE_TTL` 自然過期，不影響正確性 |
| hour=0（午夜 UTC） | key 包含 `0`，格式 `us_stock:AAPL:2026-06-14:0`，正常運作 |

---

## Impact Analysis

| 元件 | 影響 |
|------|------|
| `_fetch_premarket_price` | 加入 retry loop，行為對外不變（仍回傳 float\|None） |
| `_cache_key` | key 格式變更；舊 key 自然過期 |
| `push_us_stocks` scheduler | 間接受益（盤前取值更穩定）；無邏輯修改 |
| `/api/v1/usMessage/{id}` | cache miss 率短暫升高（舊 key 過期前）；無 API 合約改變 |
| `test_us_stock_repo.py` | 現有盤前測試需補 `PREMARKET_MAX_RETRIES` patch |
| `test_us_stock_service.py` | 新增 cache key 格式測試 |

---

## Out of Scope

- TW 股票（twstock_repo）的重試邏輯
- 將重試邏輯抽象為通用 decorator（YAGNI）
- 更改 `US_STOCK_CACHE_TTL` 的預設值
- 盤前價格的 Telegram 訊息格式調整
- Redis 連線失敗的重試
