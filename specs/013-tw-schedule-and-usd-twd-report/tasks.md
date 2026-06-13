# Tasks — Feature 013: TW Schedule Adjustment + USD→TWD Daily Report

---

## Task 013-1: 調整台股報價時間窗口起始時間

**目標**: 將 `is_tw_market_window()` 的下界從 08:30 改為 09:30。

**涉及檔案**:
- `src/fastapistock/scheduler.py` — 修改 `is_tw_market_window()` 中的常數
- `tests/test_scheduler.py` — 更新 `TestTwMarketWindow` 相關邊界測試

**變更內容**:

1. `scheduler.py`:
   - 現況: `return 8 * 60 + 30 <= minutes <= 14 * 60`
   - 目標: `return 9 * 60 + 30 <= minutes <= 14 * 60`
   - Docstring 中 `08:30–14:00` 改為 `09:30–14:00`

2. `tests/test_scheduler.py::TestTwMarketWindow`:
   - `test_window_start_0830_monday_is_in` → 測試 09:30 回傳 `True`（重命名為 `test_window_start_0930_monday_is_in`）
   - `test_before_window_0829_monday_is_out` → 測試 09:29 回傳 `False`（重命名為 `test_before_window_0929_monday_is_out`）
   - 新增 `test_at_0830_monday_is_out` 確認 08:30 在新規則下回傳 `False`

**Acceptance Criteria**:

- AC-1: `is_tw_market_window(_dt(0, 9, 30))` returns `True`
- AC-2: `is_tw_market_window(_dt(0, 9, 29))` returns `False`
- AC-3: `is_tw_market_window(_dt(0, 8, 30))` returns `False` (regression guard)
- AC-4: `is_tw_market_window(_dt(4, 14, 0))` returns `True` (end time unchanged)
- AC-5: `is_tw_market_window(_dt(4, 14, 1))` returns `False` (end time unchanged)
- AC-6: `is_tw_market_window(_dt(5, 10, 0))` returns `False` (weekend unchanged)
- AC-7: `is_us_market_window()` 所有既有測試通過（無迴歸）
- AC-8: `uv run pytest tests/test_scheduler.py` passes

---

## Task 013-2: 建立 FX Service（USD/TWD 匯率）

**目標**: 新建 `fx_service.py`，提供 `get_usd_twd_rate() -> float | None`，含 Redis cache 與失敗 fallback。

**涉及檔案**:
- `src/fastapistock/services/fx_service.py` — 新建
- `src/fastapistock/config.py` — 新增 `FX_CACHE_TTL` 與 `YFINANCE_TIMEOUT`
- `tests/test_fx_service.py` — 新建

**實作規格**:

1. `config.py` 新增:
   ```python
   FX_CACHE_TTL: int = int(os.getenv('FX_CACHE_TTL', '14400'))
   YFINANCE_TIMEOUT: int = int(os.getenv('YFINANCE_TIMEOUT', '10'))
   ```

2. `fx_service.py`:
   - Cache key: `f'fx:usd_twd:{date.today().isoformat()}'`
   - Cache TTL: `FX_CACHE_TTL`（from config）
   - Redis hit: parse `{"rate": float}` → return float
   - Redis miss: call `_fetch_live_rate()`:
     - `random.uniform(0.1, 0.4)` sleep (CLAUDE.md external API policy)
     - `yfinance.Ticker('TWD=X').history(period='1d', timeout=YFINANCE_TIMEOUT)`
     - Return last Close value as float; write to Redis
     - On any exception: log warning, return `None`
   - All functions strictly typed; no `Any`; no `print()`

**Acceptance Criteria**:

- AC-1: 第一次呼叫 `get_usd_twd_rate()` 時，若 Redis miss，呼叫 yfinance 並寫入 cache
- AC-2: 第二次呼叫（cache hit）不觸發 yfinance 呼叫
- AC-3: yfinance 拋出 `Exception` 時，函式回傳 `None` 而非 raise
- AC-4: yfinance 回傳空 DataFrame 時，函式回傳 `None`
- AC-5: 函式簽章為 `def get_usd_twd_rate() -> float | None:`
- AC-6: `uv run pytest tests/test_fx_service.py` passes（最少 4 個測試案例）
- AC-7: `uv run mypy src/fastapistock/services/fx_service.py` passes
- AC-8: `FX_CACHE_TTL` 與 `YFINANCE_TIMEOUT` 均可由環境變數覆寫（測試可注入 monkeypatch）

---

## Task 013-3: pnl_service 加入 USD→TWD 換算顯示

**目標**: 在 `build_pnl_report()` 的「美股今日」行尾插入 `(≈NT$xx,xxx)` 換算，失敗時 fallback 到原格式。

**涉及檔案**:
- `src/fastapistock/services/pnl_service.py` — 修改 `build_pnl_report()`，新增 `_fmt_us_today_line()`
- `tests/test_pnl_service.py` — 新增測試案例

**實作規格**:

1. 在 `pnl_service.py` 新增 internal helper:
   ```python
   def _fmt_us_today_line(us_today: float, rate: float | None) -> str:
       ...
   ```
   - 當 `rate is not None`: 計算 `twd_amount = round(us_today * rate)`，格式：`+US$1,257.93 (≈NT$40,883)`
   - TWD sign prefix: `+` if `twd_amount >= 0` else `''`（負值自帶 `-`）
   - TWD 使用 `f'{twd_amount:,.0f}'` 格式（千分位逗號，無小數）
   - 當 `rate is None`: 回傳原本 `_fmt_us_amount(us_today)` 字串，不附加 TWD

2. `build_pnl_report()` 修改:
   - Import `from fastapistock.services.fx_service import get_usd_twd_rate`
   - 在組裝 `us_line` 前呼叫 `rate = get_usd_twd_rate()`（`try/except` 包裹，失敗 rate = None）
   - 將 `_fmt_us_amount(us_today)` 替換為 `_fmt_us_today_line(us_today, rate)`
   - `us_holding_part` 的 `_fmt_us_amount` 呼叫**保持不變**（持倉不換算）

3. 最終組裝的 `us_line`（rate 可用時）:
   ```
   🇺🇸 美股今日：+US$1,257.93 (≈NT$40,883) ｜ 持倉：+US$54,560.84
   ```

**Acceptance Criteria**:

- AC-1: 當 `rate=32.5`、`us_today=1257.93` 時，`_fmt_us_today_line` 回傳含 `≈NT$40,883` 的字串
- AC-2: 當 `rate=None` 時，`_fmt_us_today_line` 回傳 `+US$1,257.93`（無 TWD 後綴），結果與舊 `_fmt_us_amount` 相同
- AC-3: 當 `us_today=-100.0`、`rate=32.5` 時，TWD 為 `≈NT$-3,250`（負號正確）
- AC-4: 當 `us_today=0.0`、`rate=32.5` 時，TWD 為 `≈NT$0`（sign prefix `+`）
- AC-5: `get_usd_twd_rate()` 拋出 Exception 時，`build_pnl_report()` 使用 `rate=None` fallback，報告不中斷
- AC-6: 持倉欄 `us_holding_part` 格式不變（仍為純 USD）
- AC-7: `us_today is None`（US portfolio fetch failed）路徑輸出 `🇺🇸 美股：資料讀取失敗`（既有行為不變）
- AC-8: `uv run pytest tests/test_pnl_service.py` passes（新舊測試全過）
- AC-9: MarkdownV2 escape 正確：`≈` 字元不在特殊字元清單中，`(` `)` 需 escape 為 `\(` `\)`

---

## 測試覆蓋總結

| 測試檔案 | 新增/修改 | 最低測試數 |
|---------|---------|---------|
| `tests/test_scheduler.py` | 修改 2 + 新增 1 | 既有 8 → 9 個 TW window tests |
| `tests/test_fx_service.py` | 新增 | 至少 4 個 |
| `tests/test_pnl_service.py` | 新增 | 至少 5 個 |

---

## 執行順序

013-1 和 013-2 可平行開發。013-3 依賴 013-2（`fx_service` 須先存在）。
