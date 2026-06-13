# Tasks — 015: Pre-market Cache + Retry

---

## Task 015-1: 新增 config 常數

**目標**: 在 `config.py` 新增兩個可由環境變數覆寫的常數。

**涉及檔案**: `src/fastapistock/config.py`

**實作要點**:
- 新增 `PREMARKET_MAX_RETRIES: int = int(os.getenv('PREMARKET_MAX_RETRIES', '3'))`
- 新增 `PREMARKET_RETRY_BASE_SLEEP: float = float(os.getenv('PREMARKET_RETRY_BASE_SLEEP', '1.0'))`
- 放置位置：緊接在 `YFINANCE_TIMEOUT` 之後

**Acceptance Criteria**:

- Given `PREMARKET_MAX_RETRIES` env var 未設定
- When `from fastapistock.config import PREMARKET_MAX_RETRIES`
- Then 回傳 `3`

- Given `PREMARKET_MAX_RETRIES=0` env var 設定
- When import 後取值
- Then 回傳 `0`

- Given `PREMARKET_RETRY_BASE_SLEEP=0.5` env var 設定
- When import 後取值
- Then 回傳 `0.5` (float)

- Given 執行 `uv run mypy src/` 與 `uv run ruff check .`
- When 所有 checks 執行
- Then 無新增錯誤

---

## Task 015-2: 實作盤前重試邏輯

**目標**: 在 `_fetch_premarket_price` 中加入最多 `PREMARKET_MAX_RETRIES` 次指數退避重試。

**涉及檔案**: `src/fastapistock/repositories/us_stock_repo.py`

**實作要點**:

1. 在函式頂部 import `PREMARKET_MAX_RETRIES`、`PREMARKET_RETRY_BASE_SLEEP` from config
2. ET window guard 維持在迴圈**外**最前面（不改變）
3. 現有 `try/except` 改為重試迴圈：

```python
attempt = 0
sleep_s = PREMARKET_RETRY_BASE_SLEEP
while attempt <= PREMARKET_MAX_RETRIES:
    try:
        hist = ticker.history(period='1d', interval='1m', prepost=True, timeout=_REQUEST_TIMEOUT)
        if hist.empty:
            raise ValueError('Empty pre-market history')
        # ... 現有過濾與回傳邏輯 ...
        return round(float(premarket['Close'].iloc[-1]), 2)
    except Exception as exc:
        logger.warning(
            'Pre-market fetch attempt %d/%d failed: %s',
            attempt + 1, PREMARKET_MAX_RETRIES + 1, exc,
        )
        attempt += 1
        if attempt <= PREMARKET_MAX_RETRIES:
            time.sleep(sleep_s)
            sleep_s *= 2
return None
```

4. 函式總行數不得超過 50 行；如超過，將迴圈本體抽取為 `_attempt_premarket_fetch(ticker) -> float | None`
5. Docstring 更新說明 retry 行為

**Acceptance Criteria**:

- Given ET 時間在盤前 window（04:00–09:30）
- When `ticker.history()` 首次回傳空 DataFrame，第 2 次回傳有效資料
- Then 函式回傳第 2 次的 Close 值；`time.sleep` 被呼叫 1 次，入參為 `PREMARKET_RETRY_BASE_SLEEP`

- Given ET 時間在盤前 window
- When `ticker.history()` 連續 `PREMARKET_MAX_RETRIES + 1` 次拋出 Exception
- Then 函式回傳 `None`，不 raise；`time.sleep` 被呼叫 `PREMARKET_MAX_RETRIES` 次，入參依序為 1.0、2.0、4.0

- Given ET 時間 >= 09:30（window 外）
- When 呼叫 `_fetch_premarket_price(ticker)`
- Then 直接回傳 `None`；`ticker.history` 完全不被呼叫；`time.sleep` 不被呼叫

- Given `PREMARKET_MAX_RETRIES=0`
- When `ticker.history()` 拋出 Exception
- Then 函式只嘗試 1 次後回傳 `None`；`time.sleep` 不被呼叫

- Given 執行 `uv run mypy src/`
- Then 無新增型別錯誤

---

## Task 015-3: 修改 cache key 為小時粒度

**目標**: 將 `us_stock_service._cache_key` 改為含 UTC hour 的格式。

**涉及檔案**: `src/fastapistock/services/us_stock_service.py`

**實作要點**:

1. 更新 import：加入 `datetime`、`UTC`
2. 更新 `_cache_key`:
```python
def _cache_key(symbol: str) -> str:
    now = datetime.now(UTC)
    return f'us_stock:{symbol}:{now.date().isoformat()}:{now.hour}'
```
3. Docstring 更新

**Acceptance Criteria**:

- Given UTC 時間凍結至 `2026-06-13 14:00 UTC`
- When 呼叫 `_cache_key('AAPL')`
- Then 回傳 `'us_stock:AAPL:2026-06-13:14'`

- Given UTC 時間凍結至 `2026-06-13 09:00 UTC` 與 `2026-06-13 10:00 UTC`
- When 各呼叫 `_cache_key('AAPL')` 一次
- Then 兩個 key 不相等

- Given UTC 時間凍結至 `2026-06-14 00:00 UTC`
- When 呼叫 `_cache_key('AAPL')`
- Then 回傳含 `:0` 結尾的字串（無補零）

---

## Task 015-4: 撰寫 `us_stock_repo` 重試單元測試

**目標**: 在 `tests/test_us_stock_repo.py` 覆蓋重試路徑。

**涉及檔案**: `tests/test_us_stock_repo.py`

**新增測試案例**:

| 測試函式 | 情境 |
|---------|------|
| `test_premarket_retry_succeeds_on_second_attempt` | 第 1 次空 DataFrame，第 2 次有資料 → 回傳正確價格；sleep 呼叫 1 次入參 1.0 |
| `test_premarket_retry_exhausted_returns_none` | 連續 (MAX+1) 次 Exception → None；sleep 呼叫 MAX 次，入參依序 1.0、2.0、4.0 |
| `test_premarket_retry_empty_df_all_attempts_returns_none` | 連續 (MAX+1) 次空 DataFrame → None |
| `test_premarket_no_retry_outside_window` | ET >= 09:30 → `ticker.history` 不被呼叫，sleep 不被呼叫 |
| `test_premarket_max_retries_zero_no_sleep` | `PREMARKET_MAX_RETRIES=0`，Exception → None，sleep 不被呼叫 |

**實作要點**:
- `@patch('fastapistock.repositories.us_stock_repo.time.sleep')` mock sleep
- `monkeypatch.setattr` 設定 `PREMARKET_MAX_RETRIES=3`, `PREMARKET_RETRY_BASE_SLEEP=1.0`
- 凍結 ET wall-clock 至盤前時間（例如 `08:00 ET`）

**Acceptance Criteria**:

- Given 執行 `uv run pytest tests/test_us_stock_repo.py -v`
- Then 所有測試（新增 + 既有）通過
- And 無新增 `# noqa`

---

## Task 015-5: 撰寫 `us_stock_service` cache key 單元測試

**目標**: 在 `tests/test_us_stock_service.py` 驗證新 key 格式。

**涉及檔案**: `tests/test_us_stock_service.py`（新建或既有）

**新增測試案例**:

| 測試函式 | 情境 |
|---------|------|
| `test_cache_key_format_includes_hour` | UTC 凍結至 2026-06-13 14:00 → key 為 `us_stock:AAPL:2026-06-13:14` |
| `test_cache_key_different_hours_produce_different_keys` | UTC 09:00 vs 10:00 → 兩 key 不相等 |
| `test_cache_key_midnight_hour_zero` | UTC 2026-06-14 00:00 → key 含 `:0` |

**Acceptance Criteria**:

- Given 執行 `uv run pytest tests/test_us_stock_service.py -v`
- Then 所有測試通過

---

## 執行順序

015-1（config）→ 015-2（repo retry）與 015-3（cache key）可平行 → 015-4、015-5（測試）→ 015-6（全套驗證）。

---

## 測試覆蓋總結

| 測試檔 | 新增案例數 |
|-------|---------|
| `tests/test_us_stock_repo.py` | 5 |
| `tests/test_us_stock_service.py` | 3 |
