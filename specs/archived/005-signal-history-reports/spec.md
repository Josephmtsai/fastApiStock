# Spec 005 — 訊號歷史與定期報告 (Signal History & Periodic Reports)

**狀態**: 需求確認完畢，可開發
**日期**: 2026-04-22
**依賴**: Spec 004 (Cost Level Signal) 已完成

---

## 背景與目標

Spec 004 的加碼訊號目前只在當下推播顯示，無歷史追蹤。
本功能新增兩個能力：

1. **訊號歷史**：每次觸發加碼訊號時寫入 Redis（TTL 120 天），供報告與未來分析使用
2. **定期報告**：週報（每週日 21:00）+ 月報（每月 1 日 21:00），彙整部位變化、訊號紀錄、定額進度

---

## 功能 A — 訊號歷史記錄 (Signal History)

### 寫入時機

在 `_calc_cost_signal()` 回傳非 None 時，同步寫入 Redis。

### 資料結構

**Key**: `signal:history:{market}:{symbol}:{YYYY-MM-DD}:{tier}`
- `market`: `TW` / `US`
- `symbol`: 股票代號
- `tier`: `1` / `2` / `3`（代表 ⭐ / ⭐⭐ / ⭐⭐⭐）

**Value** (JSON string):
```json
{
  "symbol": "2330",
  "market": "TW",
  "tier": 2,
  "drop_pct": -23.4,
  "price": 800.0,
  "week52_high": 1044.0,
  "ma50": 820.5,
  "timestamp": "2026-04-22T10:30:00+08:00"
}
```

**TTL**: 120 天 (10_368_000 秒)

### 去重邏輯

Key 包含日期 + tier，同一天同一檔股票同一等級只會有一筆。
等級升級（從 ⭐⭐ 變 ⭐⭐⭐）會產生新 key，兩筆並存，報告時可看到完整軌跡。

### 介面

`src/fastapistock/repositories/signal_history_repo.py`:

```python
@dataclass(frozen=True)
class SignalRecord:
    symbol: str
    market: str  # 'TW' | 'US'
    tier: int  # 1 | 2 | 3
    drop_pct: float
    price: float
    week52_high: float
    ma50: float
    timestamp: datetime  # Asia/Taipei aware

def save_signal(record: SignalRecord) -> None
def list_signals(start_date: date, end_date: date) -> list[SignalRecord]
```

---

## 功能 B — 部位快照 (Portfolio Snapshot)

### 設計

為了計算「本週/本月部位變化」，每次報告執行時：
1. 讀取當下 PnL
2. 讀取前一期快照（Redis）
3. 計算差值
4. 寫入新快照（供下次使用）

### Redis Key

- 週快照：`portfolio:snapshot:weekly:{YYYY-MM-DD}` (每個週日 21:00 產生)
- 月快照：`portfolio:snapshot:monthly:{YYYY-MM}` (每個月 1 日 21:00 產生)

### Value (JSON)

```json
{
  "pnl_tw": 523456.0,
  "pnl_us": 8345.0,
  "timestamp": "2026-04-22T21:00:00+08:00"
}
```

**TTL**: 120 天

### 首次執行處理

若前一期快照不存在，報告顯示「首次執行，尚無對比基準」，仍寫入當期快照供下次用。

---

## 功能 C — 週報 (Weekly Report)

### 觸發時機

每週日 21:00 (Asia/Taipei)，APScheduler cron job。
時間窗：本週一 00:00 ~ 週日 21:00。

### 訊息範例

```
📊 *週報* 2026-04-19 ~ 2026-04-25

── 本週部位變化 ──
台股: +23,456 TWD (本週 +0.8%)
美股: +345 USD (本週 +0.2%)
當前總損益: 台股 +523,456 TWD | 美股 +8,345 USD

── 本週加碼訊號 ──
2330 台積電: ⭐⭐ (4/22) → ⭐⭐⭐ (4/24)
AAPL: ⭐ (4/24)
（共觸發 2 檔，最嚴重 ⭐⭐⭐）

── 本月定額進度 ──
本月已買入: 85,000 / 100,000 TWD
達成率: 85%

_由 FastAPI Stock Bot 自動產生_
```

---

## 功能 D — 月報 (Monthly Report)

### 觸發時機

每月 1 日 21:00 (Asia/Taipei)，APScheduler cron job。
時間窗：**上個月** 1 日 ~ 月底。

### 訊息範例

```
📊 *月報* 2026-04

── 本月部位變化 ──
台股: +123,456 TWD (本月 +4.3%)
美股: +2,345 USD (本月 +2.8%)
當前總損益: 台股 +523,456 TWD | 美股 +8,345 USD

── 本月加碼訊號 ──
2330 台積電: ⭐⭐ (4/15) → ⭐⭐⭐ (4/22)
0050: ⭐ (4/18)
AAPL: ⭐ (4/20)
NVDA: ⭐⭐ (4/24)
（共觸發 4 檔，最嚴重 ⭐⭐⭐）

── 本月定額達成 ──
實際投入: 100,000 / 100,000 TWD
達成率: 100% ✅

_由 FastAPI Stock Bot 自動產生_
```

---

## 資料來源

| 區塊 | 來源 | 備註 |
|------|------|------|
| 當前 PnL | `portfolio_repo.fetch_pnl_tw()` / `fetch_pnl_us()` | 既有函式 |
| 前期快照 | Redis `portfolio:snapshot:weekly:*` / `monthly:*` | 本 spec 新增 |
| 加碼訊號 | Redis `signal:history:*` | Spec 004 + 本 spec 新增 |
| 定額進度 | Google Sheets 交易紀錄 tab | `GOOGLE_SHEETS_TW_TRANSACTIONS_GID` |

---

## 設計決定（已與使用者確認）

- **Q1 部位變化顯示方式**：✅ 選 B — 使用 Redis snapshot 機制計算週/月差值，並同時顯示當前絕對值
- **Q2 定額進度計算**：✅ 選 A — 本月所有買入交易加總（不區分定期/手動），目標固定 100,000 TWD
- **Q3 報告失敗處理**：✅ 選 A — 記 log 不重試
- **Q4 訊號升級軌跡**：✅ 選 A — 顯示完整升級軌跡（group by symbol，sort by date）

---

## 邊界條件

| 情境 | 處理方式 |
|------|---------|
| 週/月報區間無訊號 | 顯示「本週/月無觸發加碼訊號」 |
| Redis 連線失敗（寫訊號） | skip，log warning，不中斷推播 |
| Redis 連線失敗（讀快照） | 部位變化區塊顯示「快照讀取失敗」，其他照常 |
| 前期快照不存在（首次執行） | 顯示「首次執行，尚無對比基準」，仍寫當期快照 |
| 交易紀錄讀取失敗 | 定額進度顯示「資料讀取失敗」，報告其他區塊照常 |
| 部位 PnL 讀取失敗 | 部位區塊顯示「資料讀取失敗」，其他區塊照常 |
| 報告 scheduler job 失敗 | log error，不重試 |

---

## 不在範圍 (Out of Scope)

- 不提供報告查詢指令（`/report` 等），只推播
- 不支援使用者自訂推播時間（固定 21:00）
- 不計算產業相對強弱
- 不統計實現損益（只顯示未實現）
- 不區分定期定額 vs 手動加碼（未來交易紀錄加欄位再補）

---

## 涉及檔案

### 新增

- `src/fastapistock/repositories/signal_history_repo.py`
  - `SignalRecord` dataclass、`save_signal()`、`list_signals()`
- `src/fastapistock/repositories/portfolio_snapshot_repo.py`
  - `PortfolioSnapshot` dataclass、`save_weekly()`、`save_monthly()`、`get_weekly()`、`get_monthly()`
- `src/fastapistock/repositories/transactions_repo.py`
  - `fetch_tw_transactions()` 讀取交易紀錄 tab
  - `sum_buy_amount(year: int, month: int) -> float`
- `src/fastapistock/services/report_service.py`
  - `build_weekly_report()`、`build_monthly_report()`
  - `send_weekly_report()`、`send_monthly_report()`
- `tests/test_signal_history_repo.py`
- `tests/test_portfolio_snapshot_repo.py`
- `tests/test_transactions_repo.py`
- `tests/test_report_service.py`

### 修改

- `src/fastapistock/services/telegram_service.py`
  - `_calc_cost_signal()` 觸發時呼叫 `signal_history_repo.save_signal()`
- `src/fastapistock/scheduler.py`
  - 新增兩個 cron job（週日 21:00、每月 1 日 21:00）
- `src/fastapistock/config.py`
  - 新增 `REGULAR_INVESTMENT_TARGET_TWD: int`（預設 100_000，可由 env 調整）

### 新增 env var

```
# Monthly regular investment target in TWD (default 100000)
REGULAR_INVESTMENT_TARGET_TWD=100000
```

---

## 訊號升級軌跡邏輯

報告 build 時的處理：

```python
# 1. list_signals(start, end) 回傳 flat list
# 2. group by symbol
# 3. 每 group 依 timestamp 排序
# 4. 格式化為：{symbol}: ⭐(date) → ⭐⭐(date) → ⭐⭐⭐(date)
#    若只有一筆則只顯示單一等級
# 5. 整體最嚴重等級 = max(tier for all signals in window)
```

---

## 定額進度邏輯

```python
# 本月買入總額：
# 1. fetch_tw_transactions() 讀取交易紀錄 tab
# 2. filter: year == 當年 AND month == 本月 AND 買賣別 == '買'
# 3. sum(淨金額) 絕對值
# 4. progress_pct = total / REGULAR_INVESTMENT_TARGET_TWD * 100
```

交易紀錄欄位對應（GID=1491901018）：
- 股名 / 日期 / 成交股數 / 成本 / 買賣別 / 淨股數 / 淨金額 / 年度

需開發者讀取實際 sheet 確認 column index。

---

## 實作順序建議

1. **Phase 1**: `signal_history_repo` + 整合到 `telegram_service`（立即開始累積資料）
2. **Phase 2**: `portfolio_snapshot_repo` + `transactions_repo`
3. **Phase 3**: `report_service`（build + send）
4. **Phase 4**: `scheduler.py` 註冊 cron job

各 phase 獨立可測。Phase 1 先上可以先累積 signal history，報告做完時就有資料。
