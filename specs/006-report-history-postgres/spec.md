# Spec 006 — 報告歷史持久化 (Report History Postgres + Google Sheets Archive)

**狀態**: 需求確認完畢，可開發
**日期**: 2026-04-24
**依賴**: Spec 005 (Signal History & Periodic Reports) 已完成

---

## 背景與目標

Spec 005 的週/月報目前：
1. **Redis snapshot TTL 僅 120 天** — 無法跨年度回看歷史
2. **per-symbol 個股損益從未持久化** — `fetch_portfolio*()` 每次即時解析 CSV，歷史無從重建
3. **只推播 Telegram 純文字** — 無法做時間序列查詢、圖表、API 串接

本功能新增三個能力：

1. **Postgres 永久儲存** — 兩張表（per-symbol 明細 + report-level 彙總），永久保存
2. **Google Sheets 月度歸檔** — 月報執行後 append 到 Sheet 分頁，供肉眼 review
3. **歷史查詢通道** — `GET /api/v1/reports/history` API + Telegram `/history <symbol>` 指令

---

## 功能 A — Postgres 永久儲存 (Source of Truth)

### 寫入時機

在 `report_service.build_weekly_report()` / `build_monthly_report()` 產出結果**之後、送 Telegram 之前或之後皆可**。建議順序：

```
推播 Telegram → 寫 Postgres → (月報限定) append Google Sheet
```

三步驟互相獨立，任一失敗**不 block** 其他步驟，只 log error。

### 資料表 1：`portfolio_symbol_snapshots`（per-symbol 每期一列）

```sql
CREATE TABLE portfolio_symbol_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    report_type     VARCHAR(10) NOT NULL,          -- 'weekly' | 'monthly'
    report_period   VARCHAR(10) NOT NULL,          -- '2026-04-19' (週日) 或 '2026-04'
    market          VARCHAR(4)  NOT NULL,          -- 'TW' | 'US'
    symbol          VARCHAR(16) NOT NULL,          -- '2330' / 'AAPL'
    shares          NUMERIC(18,4) NOT NULL,
    avg_cost        NUMERIC(18,4) NOT NULL,
    current_price   NUMERIC(18,4) NOT NULL,
    market_value    NUMERIC(18,2) NOT NULL,        -- shares * current_price
    unrealized_pnl  NUMERIC(18,2) NOT NULL,        -- 本期未實現損益（幣別同 market）
    pnl_pct         NUMERIC(10,4),                 -- 損益率 %
    pnl_delta       NUMERIC(18,2),                 -- 比上期差多少；首次為 NULL
    captured_at     TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (report_type, report_period, market, symbol)
);

CREATE INDEX idx_symbol_time   ON portfolio_symbol_snapshots (market, symbol, report_period);
CREATE INDEX idx_period_report ON portfolio_symbol_snapshots (report_type, report_period);
```

### 資料表 2：`portfolio_report_summary`（每期一列）

```sql
CREATE TABLE portfolio_report_summary (
    id              BIGSERIAL PRIMARY KEY,
    report_type     VARCHAR(10) NOT NULL,
    report_period   VARCHAR(10) NOT NULL,
    pnl_tw_total    NUMERIC(18,2) NOT NULL,
    pnl_us_total    NUMERIC(18,2) NOT NULL,
    pnl_tw_delta    NUMERIC(18,2),
    pnl_us_delta    NUMERIC(18,2),
    buy_amount_twd  NUMERIC(18,2),
    signals_count   INT DEFAULT 0,
    symbols_count   INT DEFAULT 0,
    captured_at     TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (report_type, report_period)
);
```

### 冪等性

兩張表皆用 `INSERT ... ON CONFLICT (...) DO UPDATE`。重跑同一期報告只會更新既有列，不會重複。

### 型別選擇說明

- `NUMERIC` 而非 `FLOAT`：金額必須精確，避免浮點誤差
- `TIMESTAMPTZ` 而非 `TIMESTAMP`：時區安全，跨 Asia/Taipei 計算不會錯位
- `VARCHAR` 長度：`symbol` 16 足夠（含 `.TW` / `.TWO` 後綴）；`report_period` 用字串而非 `DATE`，因為月報用 `YYYY-MM` 無日

---

## 功能 B — Google Sheets 月度歸檔 (Secondary Review)

### 觸發時機

**只在月報（monthly）**執行完畢且 Postgres 寫入成功後觸發。週報不寫 Sheet（量會太大且無肉眼 review 價值）。

### 分市場不同 Tab（使用者指定）

| Market | 目標 GID | 環境變數 |
|--------|---------|----------|
| TW | `151284230` | `GOOGLE_SHEETS_HISTORY_GID_TW` |
| US | `448638367` | `GOOGLE_SHEETS_HISTORY_GID_US` |

兩個 tab 可能在同一份 Sheet (`GOOGLE_SHEETS_HISTORY_ID`)，也可能是不同 Sheet（透過 ID + GID 組合定位）。

### 寫入欄位（每月一批、一檔股票一列）

| Column | 對應 DB 欄位 |
|--------|-------------|
| report_period | `report_period` |
| symbol | `symbol` |
| shares | `shares` |
| avg_cost | `avg_cost` |
| current_price | `current_price` |
| market_value | `market_value` |
| unrealized_pnl | `unrealized_pnl` |
| pnl_pct | `pnl_pct` |
| pnl_delta | `pnl_delta` |
| captured_at | `captured_at` (ISO 8601) |

### Service Account 認證

支援 **Base64** 與 **Raw JSON** 雙模式，loader 優先讀 B64：

```python
def _load_service_account_info() -> dict:
    b64 = os.environ.get('GOOGLE_SERVICE_ACCOUNT_B64')
    if b64:
        return json.loads(base64.b64decode(b64))
    raw = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if raw:
        return json.loads(raw)
    raise RuntimeError('Google Service Account credentials not configured')
```

### 冪等與重跑

- 每次 append 前先**查詢該 tab 是否已有該 `report_period` 的資料**
- 若已存在 → 先刪除舊列再寫新列（或用 Sheet API 的 batch update 覆蓋）
- 失敗只 log warning，不 raise，不 block 主流程

---

## 功能 C — 歷史查詢 API（風格 3：混合設計）

採用「主查詢 endpoint + metadata endpoint」雙端點設計：

- `GET /api/v1/reports/history` — 查詢實際資料
- `GET /api/v1/reports/history/options` — metadata，告訴 UI 當前可選項目（給 Telegram inline keyboard 與未來前端 dropdown 用）

### C-1：`GET /api/v1/reports/history`

#### Query Parameters

| 參數 | 必填 | 預設 | 說明 |
|------|------|------|------|
| `symbol` | No | — | 股票代號；給定時走「個股時間序列」模式 |
| `market` | No | — | `TW` / `US`；給 symbol 時必填 |
| `report_type` | No | `monthly` | `weekly` / `monthly` |
| `since` | No | 1 年前 | `YYYY-MM-DD`，起始日（含） |
| `until` | No | 今日 | `YYYY-MM-DD`，結束日（含） |
| `limit` | No | 100 | 筆數上限，最大 1000 |

#### 三種查詢情境與 Response

**情境 A：個股時間序列**（給 `symbol` + `market`）

來源：`portfolio_symbol_snapshots`

```json
{
  "status": "success",
  "data": {
    "mode": "symbol",
    "symbol": "2330",
    "market": "TW",
    "report_type": "monthly",
    "records": [
      {
        "report_period": "2026-04",
        "shares": 1000.0,
        "avg_cost": 750.5,
        "current_price": 820.0,
        "market_value": 820000.0,
        "unrealized_pnl": 69500.0,
        "pnl_pct": 9.2594,
        "pnl_delta": 15000.0,
        "captured_at": "2026-05-01T21:00:00+08:00"
      }
    ]
  },
  "message": ""
}
```

**情境 B：雙市場 summary 時間序列**（無 `symbol`、無 `market`）

來源：`portfolio_report_summary`

```json
{
  "status": "success",
  "data": {
    "mode": "summary",
    "markets": ["TW", "US"],
    "report_type": "monthly",
    "records": [
      {
        "report_period": "2026-04",
        "pnl_tw_total": 523456.0,
        "pnl_us_total": 8345.0,
        "pnl_tw_delta": 23456.0,
        "pnl_us_delta": 345.0,
        "buy_amount_twd": 100000.0,
        "signals_count": 4,
        "symbols_count": 12,
        "captured_at": "2026-05-01T21:00:00+08:00"
      }
    ]
  },
  "message": ""
}
```

**情境 C：單市場 summary 時間序列**（只給 `market`，無 `symbol`）

來源：`portfolio_report_summary`，但只回該市場欄位（隱藏對方欄位以減少混淆）

```json
{
  "status": "success",
  "data": {
    "mode": "summary",
    "markets": ["TW"],
    "report_type": "monthly",
    "records": [
      {
        "report_period": "2026-04",
        "pnl_total": 523456.0,
        "pnl_delta": 23456.0,
        "buy_amount_twd": 100000.0,
        "signals_count": 3,
        "symbols_count": 8,
        "captured_at": "2026-05-01T21:00:00+08:00"
      }
    ]
  },
  "message": ""
}
```

> 註：情境 B/C **刻意不回 per-symbol 陣列**，避免 response 過大。要 per-symbol 請走情境 A。未來若有需求可加 `?group_by=symbol` flag（v2 範圍）。

#### 參數驗證規則

| 規則 | 行為 |
|------|------|
| 給 `symbol` 但未給 `market` | 400 Bad Request |
| 給 `symbol` 但 `(symbol, market)` 不存在於 DB | 200，`records: []` |
| `report_type` 非合法值 | 422 Validation Error |
| `since > until` | 400 Bad Request |
| `limit > 1000` | 422 Validation Error |

---

### C-2：`GET /api/v1/reports/history/options`

回傳當前 DB 內可選項目，供 UI 建立選單（Telegram inline keyboard / 前端 dropdown / Swagger 顯示）。

#### Response

```json
{
  "status": "success",
  "data": {
    "markets": ["TW", "US"],
    "report_types": ["weekly", "monthly"],
    "symbols": {
      "TW": ["2330", "0050", "2317"],
      "US": ["AAPL", "NVDA", "TSLA"]
    },
    "periods": {
      "weekly": ["2026-04-12", "2026-04-19", "2026-04-26"],
      "monthly": ["2026-02", "2026-03", "2026-04"]
    },
    "latest_captured_at": "2026-05-01T21:00:00+08:00"
  },
  "message": ""
}
```

#### 實作建議

- 用 `SELECT DISTINCT` 拉 symbols 與 periods，加上 `(market, symbol)` 與 `report_type` index 命中
- **加 Redis cache**（key: `reports:history:options`，TTL 600 秒）— 此資料每週/每月才變一次
- 報告寫入 Postgres 成功後 invalidate 該 cache key

### Rate Limit

兩支端點皆沿用 `RATE_LIMIT_REPORT_*`，不新增專屬變數。

---

## 功能 D — Telegram `/history` 互動式指令（Inline Keyboard）

放棄原先「純文字參數解析」設計，改為 **inline keyboard 互動式選單**，使用者全程點按、不需記股票代號。

### 互動流程

```
使用者: /history
Bot:    請選擇查詢類型：
        [ 帳戶總覽 ]  [ 個股查詢 ]

(若選「帳戶總覽」)
Bot:    請選市場：
        [ 全部 ]  [ TW ]  [ US ]
使用者: (點 TW)
Bot:    請選週期：
        [ 週 ]  [ 月 ]
使用者: (點 月)
Bot:    📊 TW 帳戶月度走勢（近 12 期）
        2025-05  +500,000  Δ —
        2025-06  +523,456  Δ +23,456
        ...

(若選「個股查詢")
Bot:    請選市場：
        [ TW ]  [ US ]
使用者: (點 TW)
Bot:    請選股票：
        [ 2330 ]  [ 0050 ]  [ 2317 ]   ← 從 /options 拉
使用者: (點 2330)
Bot:    請選週期：
        [ 週 ]  [ 月 ]
使用者: (點 月)
Bot:    📈 2330 (TW) 近 12 期月報
        ...
```

### 技術實作

#### 1. 接收 Telegram Update 的 callback_query

`webhook.py` 目前只處理 `message`，需擴充處理 `callback_query`：

```python
update = await request.json()
if 'message' in update:
    handle_message(update['message'])
elif 'callback_query' in update:
    handle_callback(update['callback_query'])
```

#### 2. callback_data 編碼

每顆按鈕的 `callback_data` 上限 64 bytes，採短碼：

```
hist:t:summary           # type = summary (帳戶總覽)
hist:t:symbol            # type = symbol (個股查詢)
hist:m:TW                # market = TW
hist:m:US                # market = US
hist:m:ALL               # market = 全部
hist:s:2330              # symbol = 2330（須記 market context）
hist:p:monthly           # period = monthly
hist:p:weekly            # period = weekly
```

#### 3. 互動 state 維護

按鈕點擊間需要記住前一步選擇（例如選了 TW 後要記住 market 才能列 symbol）。
**作法**：把已選項塞進下一輪按鈕的 callback_data：

```
hist:s:TW:2330           # 選 symbol 時把 market 一起帶
hist:p:TW:2330:monthly   # 選 period 時把 market + symbol 一起帶
```

不存 server-side session，避免狀態管理。callback_data 超 64 bytes 風險低（最長範例 27 bytes）。

#### 4. /options 資料來源

每次互動需要列選項時呼叫 `report_history_repo.list_options()`（內部走 Redis cache，TTL 600s）。

#### 5. 訊息更新

點按鈕後用 Telegram `editMessageText` 直接覆寫原訊息，避免訊息列爆炸。

### 授權與限流

- 沿用 `TELEGRAM_USER_ID` 白名單（`callback_query.from.id`）
- webhook 端點本身已有 `RATE_LIMIT_WEBHOOK_*`
- `/options` 後端有 Redis cache，DB 壓力可控

### Fallback：純文字指令

保留向後相容語法供熟手使用：

```
/history 2330           # 直接指定 symbol（auto detect market）
/history us AAPL        # 指定 market + symbol
/history                # 沒參數 → 觸發 inline keyboard
```

優先順序：有參數 → 純文字解析；無參數 → inline keyboard。

---

## 資料流

```mermaid
flowchart LR
    SCHED[APScheduler cron<br/>週日 21:00 / 月 1 日 21:00] --> RSV[report_service<br/>build_report + send]
    RSV --> TG[(Telegram)]
    RSV --> RHR[report_history_repo<br/>upsert]
    RHR --> PG[(Postgres)]
    RSV -->|monthly only| SW[sheet_writer<br/>append by market]
    SW --> TW_TAB[(Sheet tab GID<br/>TW: 151284230)]
    SW --> US_TAB[(Sheet tab GID<br/>US: 448638367)]

    API1[GET /reports/history] --> RHR2[report_history_repo<br/>query]
    API2[GET /reports/history/options] --> OPT_CACHE{Redis cache<br/>TTL 600s}
    OPT_CACHE -->|miss| RHR2
    RHR2 --> PG
    WH1[Telegram webhook<br/>/history message] --> RHR2
    WH2[Telegram webhook<br/>callback_query] --> OPT_CACHE
    WH2 --> RHR2
    RSV -.invalidate.-> OPT_CACHE
```

---

## 設計決定（已與使用者確認）

| # | 項目 | 決定 |
|---|------|------|
| 1 | 保留年限 | **永久**，不做 retention |
| 2 | 市場範圍 | **TW + US 同時**，`market` 欄位區分 |
| 3 | Google Sheet 定位 | **方案 3-B**：每月月報自動 append；TW/US 分開 tab |
| 4 | 查詢 API | **必要**：`GET /reports/history` + Telegram `/history` |
| 5 | Railway 方案 | Hobby $5/月，啟用 Postgres plugin 與自動備份 |
| 6 | 套件組合 | `psycopg[binary]>=3.2` + `sqlalchemy>=2.0` + `alembic>=1.13` + `gspread>=6.0` |
| 7 | Redis snapshot 處置 | **保留不動**，繼續做「上一期對比」的短期熱快取 |
| 8 | Backfill | **不做**，從此刻累積；前 4 週 `pnl_delta` 可為 NULL |

---

## 功能 G — Service Pipeline 整合（Phase 3 詳細設計）

### G-1：設計目標

把 Phase 2 的 repository 層 + 既有 `build_weekly_report()` / `build_monthly_report()` 串成一條**可重入、可單測、可手動觸發**的流水線。三個呼叫者（cron / 手動 trigger endpoint / 一次性 backfill 腳本）共用同一個 entry point：`run_report_pipeline()`。

### G-2：`run_report_pipeline()` 簽名

```python
from datetime import datetime
from dataclasses import dataclass
from typing import Literal

ReportType = Literal['weekly', 'monthly']
Trigger = Literal['cron', 'manual', 'backfill']


def run_report_pipeline(
    *,
    report_type: ReportType,
    report_period: str | None = None,
    trigger: Trigger = 'cron',
    dry_run: bool = False,
    skip_telegram: bool = False,
    skip_sheet: bool = False,
    now: datetime | None = None,
) -> 'RunReportResult':
    """Execute a single report build + persist + (optional) Telegram + Sheet flow."""
```

#### `report_period` 自動推算規則

| `report_type` | `report_period=None` 時 | 對應 spec-005 既有 helper |
|---------------|------------------------|--------------------------|
| `'weekly'` | `_weekly_window(now).snapshot_id`（最近一個週日，例 `'2026-04-19'`） | `report_service._weekly_window` |
| `'monthly'` | `_monthly_window(now).snapshot_id`（前一個月，例 `'2026-03'`） | `report_service._monthly_window` |

顯式給定時須走 `^\d{4}-\d{2}(-\d{2})?$` 正則驗證，格式不符 → `ValueError`。

### G-3：`RunReportResult` Dataclass

```python
@dataclass(frozen=True)
class RunReportResult:
    job_id: str                     # uuid.uuid4().hex[:8]
    report_type: ReportType
    report_period: str
    trigger: Trigger
    dry_run: bool
    telegram_sent: bool
    postgres_ok: bool
    sheet_ok: bool | None           # 月報才有意義；週報 / dry_run / skip_sheet 為 None
    symbol_rows_written: int
    summary_written: bool
    duration_ms: int
    errors: list[str]
```

對齊 E-2 trigger response：`job_id` / `postgres_ok` / `sheet_ok` / `telegram_sent` / `symbol_rows_written` / `duration_ms` 完全沿用。

### G-4：Pipeline 執行順序與失敗行為

```mermaid
sequenceDiagram
    autonumber
    participant Caller as Caller (cron / endpoint / backfill)
    participant Pipe as run_report_pipeline()
    participant RS as report_service.build_*_report()
    participant TG as Telegram API
    participant PG as report_history_repo
    participant SH as sheet_writer

    Caller->>Pipe: report_type, report_period, flags
    Note over Pipe: job_id = uuid4().hex[:8]<br/>logger = LoggerAdapter(extra={job_id, trigger})
    Pipe->>Pipe: log 'report_history.build.start'

    Pipe->>RS: build markdown + collect raw fetches
    RS-->>Pipe: markdown_text, fetch_results

    alt dry_run == True
        Pipe->>Pipe: log 'report_history.build.dry_run_preview'
        Pipe-->>Caller: RunReportResult(dry_run=True, all flags=False)
    else normal flow

        rect rgb(240, 250, 240)
            Note over Pipe,TG: Step 1 — Telegram (skip if skip_telegram)
            alt skip_telegram == False
                Pipe->>TG: _send_markdown(markdown_text)
                TG-->>Pipe: ok / fail
            end
            Note right of Pipe: Telegram 失敗也繼續走 Step 2/3
        end

        rect rgb(240, 245, 255)
            Note over Pipe,PG: Step 2 — Postgres (Decimal conversion)
            Pipe->>Pipe: _build_symbol_snapshots / _build_summary<br/>(此處 float→Decimal(str))
            Pipe->>PG: upsert_symbol_snapshots(rows)
            Pipe->>PG: upsert_report_summary(row)
            Note right of Pipe: 任一 upsert raise → catch、postgres_ok=False<br/>仍進 Step 3
        end

        rect rgb(255, 250, 240)
            Note over Pipe,SH: Step 3 — Sheet (monthly only, skip if weekly/skip_sheet)
            alt report_type == 'monthly' AND not skip_sheet
                Pipe->>SH: append_monthly_history('TW', tw_rows)
                Pipe->>SH: append_monthly_history('US', us_rows)
            else
                Pipe->>Pipe: sheet_ok = None
            end
        end

        Pipe->>Pipe: log 'report_history.build.done'
        Pipe-->>Caller: RunReportResult(...)
    end
```

#### 失敗行為總表

| Step | 失敗時機 | 處理 | 影響後續 |
|------|----------|------|---------|
| Build markdown | `_safe_call` 內 fetch 失敗回 `None` | 繼續 | 不影響 |
| Telegram send | `_send_markdown` catch httpx error 回 False | log warning，`telegram_sent=False` | **不影響** Postgres / Sheet |
| Postgres upsert | `SQLAlchemyError` | catch、`postgres_ok=False`、`errors.append('SQLAlchemyError')` | **不影響** Sheet |
| Sheet append | `sheet_writer` 內部已 catch 回 False | 讀回傳值 → `sheet_ok=False` | 流程結束 |

**核心原則**：pipeline 主體**永不 raise**，所有錯誤透過 `RunReportResult.errors` 與 log 上報。

### G-5：`job_id` 與 LoggerAdapter 規範

| 規則 | 說明 |
|------|------|
| `job_id` 生成位置 | **`run_report_pipeline()` 函式頂端** |
| 傳遞範圍 | 僅在 `services/report_service.py` 內部；**不下沉到 repository 層** |
| Repository log | 維持獨立 namespace（`fastapistock.report_history.repo.*`），**不接收 `job_id`**；Railway dashboard 用時間範圍 + namespace grep 串連 |
| `extra` 欄位 | 至少 `job_id`、`trigger`、`report_type`、`report_period` |

#### Pipeline log 事件清單（補充 E-1）

| 事件 | Level | 觸發時機 |
|------|-------|----------|
| `report_history.build.start` | INFO | pipeline 進入 |
| `report_history.build.dry_run_preview` | INFO | dry_run 完成 build |
| `report_history.build.telegram.skipped` | INFO | `skip_telegram=True` |
| `report_history.build.telegram.ok` | INFO | Telegram 推送成功 |
| `report_history.build.telegram.fail` | WARNING | Telegram 推送失敗 |
| `report_history.build.postgres.fail` | ERROR | Postgres step catch |
| `report_history.build.sheet.skipped` | INFO | 週報或 `skip_sheet=True` |
| `report_history.build.done` | INFO | pipeline 結束 |

### G-6：Decimal 轉換邊界

**原則**：保留所有既有 repo / Redis 層的 `float`，僅在 `report_service.py` 進入 Postgres path 的**邊界**做 `Decimal(str(value))` 一次性轉換。

#### 需要在 `report_service.py` 新增的轉換點

| 位置 | 來源 | 目標 |
|------|------|------|
| `_build_symbol_snapshots()` | `PortfolioEntry.shares: int` / `avg_cost: float` / `unrealized_pnl: float` | `SymbolSnapshot.*: Decimal` |
| 同上 | `current_price`：US 由 `us_stock_service.get_us_stocks()` 取，TW 由 `stock_service.get_rich_tw_stocks()` 取（**Phase 3 新引入的 cross-service dependency**） | `SymbolSnapshot.current_price: Decimal` |
| 同上 | 計算 `market_value` / `pnl_pct` / `pnl_delta` | 全程 Decimal 算術 |
| `_build_summary()` | `fetch_pnl_tw()` / `fetch_pnl_us()` 回 `float \| None` | `pnl_*_total: Decimal`（None 跳過寫入 + `errors.append('pnl_fetch_failed')`） |
| 同上 | `transactions_repo.sum_buy_amount() -> float` | `buy_amount_twd: Decimal \| None` |
| 同上 | `signal_history_repo.list_signals()` count → int | `signals_count: int` |
| 同上 | `prev_snapshot.pnl_tw / pnl_us`（Redis 的 float） | 算 `pnl_*_delta` 用 |

#### 禁止事項
- **禁止** `Decimal(float_value)` 直轉（會引入 binary float 漂移）
- **禁止**改 `portfolio_repo` / `transactions_repo` / `redis_cache` 回傳型別
- **禁止**在 repository 層做 Decimal 轉換

### G-7：對既有 cron job 的影響（scheduler.py）

| 改動 | 細節 |
|------|------|
| 替換 cron callable | `send_weekly_report` → `lambda: run_report_pipeline(report_type='weekly', trigger='cron')`<br>`send_monthly_report` → `lambda: run_report_pipeline(report_type='monthly', trigger='cron')` |
| `_scheduled_push` (interval 30min) | **不動**，與報告無關 |
| `send_weekly_report` / `send_monthly_report` | **直接刪除**（已 grep 確認僅 scheduler 引用） |

### G-8：與既有 `build_*_report()` 的關係

**結論：包裝（wrap），不取代。**

理由：build 函式仍負責「產出 MarkdownV2 + 持久化 Redis 上一期 snapshot」（spec-005 行為）。`run_report_pipeline()` 的職責是**編排**：呼叫 build → 推 Telegram → 組 SymbolSnapshot → 寫 Postgres → 寫 Sheet → 回傳 result。

**重構**：把 `build_*_report` 內部「順手寫 Redis snapshot」抽成 `_persist_redis_snapshot()` helper，讓 pipeline 在 `dry_run` 時跳過。原 build 函式回傳改為 `(markdown_text, fetch_results)` tuple，避免 pipeline 重複抓資料。

### G-9：Phase 3 不在範圍

- ❌ Trigger endpoint `POST /reports/history/trigger`（Phase 5）
- ❌ History query endpoints（Phase 4）
- ❌ Telegram `/history` 互動（Phase 4）
- ❌ Backfill script（Phase 6，但已設計成可呼叫 `run_report_pipeline(trigger='backfill')`）
- ❌ 改 `portfolio_repo` / `transactions_repo` 為 Decimal（範圍過大）

---

## 功能 E — 可觀測性與手動觸發 (Observability & Manual Trigger)

### E-1：結構化日誌規格

所有寫入動作必須輸出結構化 log，方便 Railway dashboard 直接 grep 確認。

| 事件 | Level | 訊息格式（建議用 logger extra 帶結構化欄位） |
|------|-------|--------------------------------------------|
| 開始建立報告 | INFO | `report_history.build.start` + `{report_type, report_period, trigger='cron'\|'manual', job_id}` |
| Postgres upsert 成功 | INFO | `report_history.postgres.upsert.ok` + `{report_type, report_period, symbol_rows, summary_rows, duration_ms}` |
| Postgres upsert 失敗 | ERROR | `report_history.postgres.upsert.fail` + `{report_type, report_period, error_type, error_message}` |
| Sheet append 開始 | INFO | `report_history.sheet.append.start` + `{market, gid, rows}` |
| Sheet append 成功 | INFO | `report_history.sheet.append.ok` + `{market, gid, rows, duration_ms}` |
| Sheet append 失敗 | WARNING | `report_history.sheet.append.fail` + `{market, gid, error_type, error_message}` |
| 完整流程結束 | INFO | `report_history.build.done` + `{report_type, report_period, postgres_ok, sheet_ok, total_duration_ms}` |
| 查詢 API 命中 | INFO | `report_history.api.query` + `{mode, symbol, market, report_type, records}` |

#### 實作要求

- 統一用 `logger = logging.getLogger('fastapistock.report_history')`，獨立 namespace 方便 Railway 過濾
- `job_id` 用 `uuid.uuid4().hex[:8]` 產生，**同一次 build 流程的所有 log 共用**，方便串連
- 失敗 log 必須帶 `error_type` (例如 `psycopg.OperationalError`、`gspread.exceptions.APIError`) 與完整 `error_message`，**不要吃掉 stack trace**
- Service Account loader 啟動時若 disabled 要 log 一次 WARNING：`report_history.sheet.disabled` + `{reason}`

#### Railway 端驗證指令

```bash
# 在 Railway dashboard 的 Logs tab 過濾
report_history.postgres.upsert.ok
report_history.sheet.append.ok
report_history.build.done
```

### E-2：手動觸發端點 `POST /api/v1/reports/history/trigger`

提供管理員手動跑一次 build+save 流程，用於：
- 第一次部署後驗證寫入鏈路
- 排程失敗後補跑
- 建立歷史 baseline（例如把當前持倉打成 `2026-03` 標籤）

#### Request Body

```json
{
  "report_type": "monthly",
  "report_period": "2026-03",
  "dry_run": false,
  "skip_telegram": true,
  "skip_sheet": false
}
```

| 欄位 | 必填 | 預設 | 說明 |
|------|------|------|------|
| `report_type` | Yes | — | `weekly` / `monthly` |
| `report_period` | No | 當期 | 自訂期間標籤（YYYY-MM-DD 或 YYYY-MM）；用於 baseline 建立 |
| `dry_run` | No | `false` | `true` 時只 build + log preview，不寫 DB / Sheet |
| `skip_telegram` | No | `true` | 避免測試時打擾收件者 |
| `skip_sheet` | No | `false` | 排查 Sheet API 問題時可關 |

#### Response

```json
{
  "status": "success",
  "data": {
    "job_id": "a3f2c91e",
    "report_type": "monthly",
    "report_period": "2026-03",
    "dry_run": false,
    "postgres_ok": true,
    "sheet_ok": true,
    "telegram_sent": false,
    "symbol_rows_written": 12,
    "duration_ms": 4523
  },
  "message": ""
}
```

#### 授權

- 必須帶 `Authorization: Bearer <ADMIN_TOKEN>` header
- `ADMIN_TOKEN` 由環境變數提供（新增）；未設定則此端點返回 503，避免裸機暴露
- 沿用 `RATE_LIMIT_REPORT_*` 限流（避免暴力觸發拖垮 yfinance）

#### 安全考量

- 端點不接受任意 SQL / Sheet 寫入參數，只走既有 `report_service.build_*` 流程
- `report_period` 接受任意字串會造成髒資料 → 後端用正則驗證：`^\d{4}-\d{2}(-\d{2})?$`
- 同一 `(report_type, report_period)` 重跑走 UPSERT，不會重複建列

### E-3：3 月資料 Baseline 建立流程（使用者執行）

**前提**：本 spec **不做真實歷史回填**（不重抓 3 月底 yfinance 價格）。3 月 baseline 的本質是「以當下持倉狀態當作 3 月月底快照」。

**步驟**：

1. 部署完畢、確認 `/api/v1/reports/history/options` 可正常回應（DB 通）
2. 執行 dry run 確認資料正確：
   ```bash
   curl -X POST https://your-app.up.railway.app/api/v1/reports/history/trigger \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"report_type":"monthly","report_period":"2026-03","dry_run":true,"skip_telegram":true}'
   ```
3. 看 Railway log 確認 `report_history.build.start` 與 build preview 內容無誤
4. 真實寫入：
   ```bash
   curl -X POST https://your-app.up.railway.app/api/v1/reports/history/trigger \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"report_type":"monthly","report_period":"2026-03","dry_run":false,"skip_telegram":true,"skip_sheet":false}'
   ```
5. 確認 log：`report_history.postgres.upsert.ok` + `report_history.sheet.append.ok` 都有
6. 用 `GET /api/v1/reports/history/options` 確認 `periods.monthly` 包含 `2026-03`

**重要警語（會寫進報告 metadata）**：
- 表 1 的 `current_price` 為**觸發當下價格**，不代表 3 月底實際收盤
- 表 1 的 `pnl_delta` 為 NULL（無前期資料可比對）
- 4 月正式月報跑完後，`pnl_delta` 才會從 4 月起算

### E-4：新增環境變數

```env
# 手動觸發端點授權 token（建議用 openssl rand -hex 32 產生）
# 未設定時 /trigger 端點返回 503
ADMIN_TOKEN=
```

---

## 功能 F — 一次性歷史 Backfill 腳本（2026-01 / 02 / 03）

### F-1 目標

部署後一次性把 2026 年 1、2、3 月的月度 snapshot 補進 DB，作為後續每月正式報告的 baseline。**只跑一次**。

### F-2 「跑一次」的執行方式

採用**獨立 Python script** 放在 `scripts/backfill_history.py`，**不掛在 scheduler、不暴露為 HTTP endpoint**。執行採 **Railway CLI `railway run`**（在本機終端執行，但 Railway 環境變數自動注入，連到 Railway Postgres）。

#### 為什麼不掛在 endpoint
- 一次性任務，不應與 production 端點共存（避免誤觸發）
- 跑時會打 yfinance 歷史 API 數十次，需要 random delay 1-2 秒，HTTP 端點 timeout 會中斷
- 跑完用 `git rm` 移除腳本即可，spec 的 phase 6 完成後刪除 task

#### 執行步驟（Railway CLI）

```bash
# 一次性安裝 Railway CLI（之後不用重做）
npm i -g @railway/cli
# 或 PowerShell:  iwr -useb https://railway.app/install.ps1 | iex

# 登入（會開瀏覽器）
railway login

# 在本專案根目錄執行，連結 Railway project
railway link

# Step 1: dry-run 確認重建邏輯（不寫 DB / Sheet）
railway run python -m fastapistock.scripts.backfill_history \
  --months 2026-01,2026-02,2026-03 \
  --markets TW,US \
  --dry-run \
  --verbose

# Step 2: 看 log 確認每月 symbols / shares / pnl 數字合理

# Step 3: 真實寫入
railway run python -m fastapistock.scripts.backfill_history \
  --months 2026-01,2026-02,2026-03 \
  --markets TW,US

# Step 4: 驗證
curl https://你的-app.up.railway.app/api/v1/reports/history/options \
  | jq '.data.periods.monthly'
# 應包含 ["2026-01", "2026-02", "2026-03"]
```

#### `railway run` 的運作原理
- script 在**本機 venv** 執行（用本機 git 最新 code）
- Railway 把 production 環境變數（`DATABASE_URL` / `GOOGLE_SERVICE_ACCOUNT_*` 等）**注入到本機 shell**
- 連線走公網到 Railway Postgres（有 100-300ms 延遲，但對一次性任務無感）
- 本機 terminal 不關 = 任務不中斷

### F-3 持倉重建邏輯

```
給定 month_end_date (例: 2026-01-31)：
  1. 從 transactions_repo 抓所有交易，filter date <= month_end_date
  2. 按 symbol group，依時序累積：
     - 買入：shares += qty；avg_cost = weighted average
     - 賣出：shares -= qty；avg_cost 不變（簡化：不做 FIFO）
  3. 過濾 shares > 0 的 symbol（已賣光的不寫入歷史）
  4. 對每個剩餘 symbol：
     - 從 yfinance 拉 month_end_date 收盤價（若該日為週末則取最近交易日）
     - 計算 market_value = shares * close_price
     - 計算 unrealized_pnl = (close_price - avg_cost) * shares
     - 計算 pnl_pct = unrealized_pnl / (avg_cost * shares) * 100
  5. UPSERT 到 portfolio_symbol_snapshots（report_type='monthly', report_period='2026-01' 等）
  6. 彙總當月 summary 寫入 portfolio_report_summary
```

### F-4 月底日期定義

| 月份 | month_end_date | 備註 |
|------|---------------|------|
| 2026-01 | 2026-01-31（六） | yfinance 自動回 2026-01-30（五）收盤價 |
| 2026-02 | 2026-02-28（六） | yfinance 自動回 2026-02-27（五）收盤價 |
| 2026-03 | 2026-03-31（二） | 直接使用 |

實作上呼叫 `ticker.history(start=month_end, end=month_end + 5days)` 取第一筆有效收盤價。

### F-5 歷史價來源與 Rate Limit

- **TW 股票**：`yfinance.Ticker(f'{symbol}.TW')` 或 `.TWO`
- **US 股票**：`yfinance.Ticker(symbol)`
- 每支 symbol × 每月 = 一次 API 呼叫；TW 之間加 `random.uniform(1.0, 2.5)` 秒延遲
- 估算成本：假設 TW 10 檔 + US 5 檔 = 15 symbols × 3 months = 45 calls，台股延遲下總計約 60-90 秒

### F-6 pnl_delta 計算順序

腳本必須**按月份順序執行**才能正確算 delta：

| month | pnl_delta 計算 |
|-------|---------------|
| 2026-01 | NULL（首月無前期） |
| 2026-02 | 02 月 PnL − 01 月 PnL |
| 2026-03 | 03 月 PnL − 02 月 PnL |

腳本內部對 `--months` 參數先 sort，依序寫入。

### F-7 Summary 表填充

| 欄位 | 來源 |
|------|------|
| `pnl_tw_total` / `pnl_us_total` | 該月 TW / US 個股 unrealized_pnl 加總 |
| `pnl_tw_delta` / `pnl_us_delta` | 與前一月差值（首月 NULL） |
| `buy_amount_twd` | `transactions_repo.sum_buy_amount(year, month)` 該月買入金額 |
| `signals_count` | **固定 0**（歷史訊號無法重建） |
| `symbols_count` | 該月有持倉的 symbol 數量 |
| `captured_at` | month_end_date 的 21:00 +08:00（模擬正常 schedule 時間） |

### F-8 假設、限制與已知偏差

**必須在腳本啟動時 log warning 提示使用者**：

1. **交易紀錄必須完整且按時序**：若 Google Sheet 漏記交易，重建持倉會錯
2. **不處理 FIFO 賣出**：賣出時 avg_cost 不變，與真實會計差異存在
3. **不處理股票分割**：yfinance close price 已 split-adjusted，但 transactions sheet 的 avg_cost 通常未調整 → 經歷過 split 的部位會有誤差
4. **不處理股息**：未實現損益不含股息收益
5. **不處理已賣光部位**：歷史 snapshot 不會包含當月已清倉的 symbol
6. **歷史訊號無法重建**：`signals_count` 一律為 0
7. **yfinance 歷史價有 lag**：尾盤大跌等盤後事件可能不反映

### F-9 腳本介面與 CLI 參數

```
usage: backfill_history.py [-h]
  --months MONTHS              # 必填，逗號分隔 YYYY-MM
  [--markets {TW,US,BOTH}]     # 預設 BOTH
  [--dry-run]                  # 只 build 不寫 DB
  [--skip-sheet]               # 不 append Sheet
  [--symbols SYMBOLS]           # 可選，限定 symbols（debug 用）
  [--verbose]                   # log level DEBUG
```

執行時輸出進度 log（沿用 `report_history.*` namespace + 額外 `trigger='backfill'`），方便 grep 確認。

### F-10 驗證流程

完整指令見 F-2「執行步驟」。簡述：

1. `railway run ... --dry-run --verbose` 看 log 確認重建邏輯
2. `railway run ...`（不帶 --dry-run）寫入
3. `curl /api/v1/reports/history/options` 確認 `periods.monthly` 含 `["2026-01", "2026-02", "2026-03"]`
4. `curl /api/v1/reports/history?report_type=monthly` 確認三筆 summary 且 `pnl_delta` 從 2026-02 起有值

---

## 邊界條件與失敗處理

| 情境 | 處理方式 |
|------|---------|
| Postgres 連線失敗 | log error，Telegram 推播照常；下次 report 自動 retry |
| Google Sheets API 失敗 | log warning，不 block；月報 Telegram + Postgres 已完成 |
| Service Account 未設定 | 啟動時 log warning，Sheet 寫入功能 disabled（Postgres 仍正常） |
| 重跑同期報告 | UPSERT 冪等；Sheet 端先刪後寫 |
| `symbol` 不存在於歷史 | API 回 `data.records: []`，Telegram 回「查無資料」 |
| 首次執行（無前期） | `pnl_delta` NULL；Telegram 顯示「—」 |
| Railway Postgres 超量（Hobby 1GB） | 手動檢查（估算 10 年 < 10 MB，無此風險） |

---

## 不在範圍 (Out of Scope)

- ❌ ~~歷史回填~~ → **改為功能 F**：限定 2026-01/02/03 三個月，一次性 script
- ❌ 多年度歷史回填（>3 個月或跨年） — 仍不在範圍
- ❌ 自動 retention / 清理舊資料 — 永久保存
- ❌ 前端圖表 UI — API 已提供 JSON，前端為另一個 spec
- ❌ 實現損益（realized_pnl）— 本 spec 只記未實現
- ❌ 股利（dividend）追蹤
- ❌ 股票分割（split）調整 — 經歷 split 的部位 backfill 會有誤差
- ❌ 週報寫 Google Sheet — 只月報寫
- ❌ 歷史訊號（signal）回填 — `signals_count` 一律為 0

---

## 涉及檔案

### 新增

- `alembic/` 目錄（init by `uv run alembic init alembic`）
  - `alembic.ini`、`env.py`、`versions/0001_initial_snapshot_tables.py`
- `src/fastapistock/repositories/report_history_repo.py`
  - `SymbolSnapshot` / `ReportSummary` dataclass
  - `upsert_symbol_snapshots()` / `upsert_report_summary()`
  - `list_symbol_history()` / `list_summary_history()`
- `src/fastapistock/repositories/sheet_writer.py`
  - `_load_service_account_info()`（B64 + JSON 雙模式）
  - `append_monthly_history(market, rows)`（依 market 寫不同 GID）
- `src/fastapistock/db/` 目錄
  - `engine.py`（SQLAlchemy engine + session factory，讀 `DATABASE_URL`）
  - `models.py`（`PortfolioSymbolSnapshot` / `PortfolioReportSummary` ORM models）
- `tests/test_report_history_repo.py`
- `tests/test_sheet_writer.py`
- `tests/test_history_api.py`
- `tests/test_backfill_history.py`（測重建邏輯與時序計算，yfinance 用 mock）
- `scripts/backfill_history.py`（功能 F；驗證完成後可移除）
- `docker-compose.dev.yml`（可選：本機 Postgres + Redis 一把起）

### 修改

- `pyproject.toml`
  - 新增 `psycopg[binary]>=3.2`、`sqlalchemy>=2.0`、`alembic>=1.13`、`gspread>=6.0`
- `src/fastapistock/config.py`
  - 新增 `DATABASE_URL`、`GOOGLE_SERVICE_ACCOUNT_JSON`、`GOOGLE_SERVICE_ACCOUNT_B64`
  - 新增 `GOOGLE_SHEETS_HISTORY_ID`、`GOOGLE_SHEETS_HISTORY_GID_TW`、`GOOGLE_SHEETS_HISTORY_GID_US`
- `src/fastapistock/services/report_service.py`
  - `build_weekly_report()` / `build_monthly_report()` 收尾處新增 DB upsert
  - `build_monthly_report()` 另外呼叫 `sheet_writer.append_monthly_history()`
  - 新增 `run_report_pipeline(report_type, report_period, dry_run, skip_telegram, skip_sheet)` 統一介面，供 cron 與手動觸發共用
  - 各步驟產生統一 `job_id` 並 log 結構化事件（`report_history.*` namespace）
- `src/fastapistock/routers/reports.py`
  - 新增 `GET /api/v1/reports/history` endpoint
  - 新增 `GET /api/v1/reports/history/options` endpoint（含 Redis cache）
  - 新增 `POST /api/v1/reports/history/trigger` 手動觸發 endpoint（Bearer token 授權）
- `src/fastapistock/routers/webhook.py`
  - 新增 `/history` 純文字指令 handler（fallback 路徑）
  - 新增 `callback_query` 處理路徑（inline keyboard 互動流程）
  - 新增 callback_data 編碼/解碼工具（短碼 prefix `hist:*`）
- `src/fastapistock/main.py`
  - lifespan startup 時驗證 `DATABASE_URL` 連線（fail fast）
- `.env.example` ✅ 已更新
- `Procfile` / `railway.json`（如有）
  - 加 `release: alembic upgrade head` 或 app startup hook

---

## 環境變數（.env.example 已更新）

```env
# Postgres
DATABASE_URL=postgresql://user:pass@host:port/db

# Google Service Account（B64 或 JSON 二擇一）
GOOGLE_SERVICE_ACCOUNT_JSON=
GOOGLE_SERVICE_ACCOUNT_B64=

# 歷史歸檔 Sheet
GOOGLE_SHEETS_HISTORY_ID=
GOOGLE_SHEETS_HISTORY_GID_TW=151284230
GOOGLE_SHEETS_HISTORY_GID_US=448638367

# 手動觸發 trigger 端點授權 token
# 產生: openssl rand -hex 32
ADMIN_TOKEN=
```

---

## 實作順序建議

### Phase 1 — Infrastructure
1. 加套件依賴，本機 `uv sync`
2. `docker-compose.dev.yml` 起本機 Postgres
3. `alembic init` + 寫初始 migration
4. `db/engine.py` + `db/models.py`
5. 本機 `alembic upgrade head` 驗證表建立成功

### Phase 2 — Repository
6. `report_history_repo.py`（upsert + list）
7. `sheet_writer.py`（credentials loader + append by market）
8. 單元測試（用 `testcontainers` 或 SQLite in-memory 替代）

### Phase 3 — Service Pipeline 整合（詳細設計見功能 G）

> 抽 `run_report_pipeline()` 統一 entry，整合 Telegram + Postgres + Sheet 三步驟。**Routers 不在 Phase 3 範圍**。

#### Task 9 — `config.py` 新增環境變數
- 檔案：`src/fastapistock/config.py`
- 改動：新增 `DATABASE_URL` / `GOOGLE_SERVICE_ACCOUNT_JSON` / `GOOGLE_SERVICE_ACCOUNT_B64` / `GOOGLE_SHEETS_HISTORY_ID` / `GOOGLE_SHEETS_HISTORY_GID_TW` / `GOOGLE_SHEETS_HISTORY_GID_US` / `ADMIN_TOKEN` 讀取
- 驗收：`tests/test_config.py` 覆蓋新欄位

> **Phase 1 已完成**

#### Task 10 — `main.py` lifespan DB 連線驗證
- 檔案：`src/fastapistock/main.py`
- 改動：lifespan startup 加 `engine.connect() + SELECT 1`，失敗 log ERROR 但**不 fail fast**
- 驗收：`tests/test_main_lifespan.py` mock engine 驗證連線成功 / 失敗 log

> **Phase 1 已完成**

#### Task 11 — 抽出 `RunReportResult` dataclass
- 檔案：`src/fastapistock/services/report_service.py`
- 改動：新增 `RunReportResult` frozen dataclass + `ReportType` / `Trigger` Literal alias（簽名見 G-3）
- 驗收：`from fastapistock.services.report_service import RunReportResult` 可正常 import

#### Task 12 — 重構 `build_*_report()` 抽出 fetch results
- 檔案：`src/fastapistock/services/report_service.py`
- 改動：
  1. 新增 private dataclass `_FetchResults`
  2. 抽 `_collect_fetch_results(window, now) -> _FetchResults`
  3. 抽 `_persist_redis_snapshot(window, fetch_results)`
  4. 改 `_build_report(window, now)` 回傳為 `tuple[str, _FetchResults]`
- 驗收：既有 `tests/test_report_service.py` 全綠；新測試驗證 `dry_run=True` 時 `_persist_redis_snapshot` 不被呼叫

#### Task 13 — 新增 `_build_symbol_snapshots()` / `_build_summary()`
- 檔案：`src/fastapistock/services/report_service.py`
- 改動：兩個 private helper：
  - `_build_symbol_snapshots(window, fetch_results, market) -> list[SymbolSnapshot]`：對 TW/US 分別組裝 per-symbol Decimal rows；**內含 `Decimal(str(...))` 轉換**；`current_price` 由 `stock_service` / `us_stock_service` 取得
  - `_build_summary(window, fetch_results, snapshot_rows) -> ReportSummary`
- 驗收：單測涵蓋（a）正常組裝全 Decimal、（b）`pnl_tw=None` → 跳過寫入 + `errors.append`、（c）空 portfolio → `[]`、（d）TW + US 混合

#### Task 14 — `run_report_pipeline()` 主函式
- 檔案：`src/fastapistock/services/report_service.py`
- 改動：實作完整 pipeline（簽名見 G-2、流程見 G-4）：
  - 頂端產 `job_id`、建 `LoggerAdapter`、log `build.start`
  - 呼叫 `_collect_fetch_results` + `_build_report` 拿 markdown
  - `dry_run` log preview 後 return
  - Step 1 Telegram（含 `skip_telegram` 短路）
  - Step 2 組 snapshot/summary → repo upsert（catch `SQLAlchemyError`）
  - Step 3 月報 + 非 `skip_sheet` → sheet_writer
  - 計算 `duration_ms`，log `build.done`，回 `RunReportResult`
- 驗收：`tests/test_report_pipeline.py` 至少 12 個 case：
  - dry_run 時三 step 都不被呼叫
  - skip_telegram=True 時 Postgres 仍跑
  - Postgres raise 時 Sheet 仍跑（月報）
  - 週報情境 `sheet_ok=None`
  - Telegram 失敗時其餘 step 不受影響
  - `report_period=None` 自動填當期
  - `report_period='2026-03'` 顯式指定
  - `report_period='bad-format'` raise `ValueError`
  - `errors` 在無錯時為空 list
  - `LoggerAdapter` 注入 `job_id`
  - Decimal 邊界：mock fetch float `0.1` → 傳給 repo 應為 `Decimal('0.1')`
  - `trigger='backfill'` log extra 標籤正確

#### Task 15 — `scheduler.py` 改用 `run_report_pipeline()`
- 檔案：`src/fastapistock/scheduler.py`
- 改動：移除 `send_*_report` import，改用 `run_report_pipeline`；**直接刪除** 原 `send_weekly_report` / `send_monthly_report`（grep 確認僅 scheduler 引用）
- 驗收：`tests/test_scheduler.py` mock 驗證 `run_report_pipeline` 被以正確參數呼叫；既有排程時間不變

#### Task 16 — Pipeline 整合測試
- 檔案：`tests/test_report_pipeline_integration.py`（新檔）
- 改動：SQLite in-memory + mock httpx + mock gspread 端到端：
  - cron 呼 `run_report_pipeline('weekly', trigger='cron')` → 驗 Postgres 兩張表 + Redis snapshot + Telegram mock 各被呼叫
  - 月報情境額外驗 sheet_writer.append_monthly_history 被呼叫 2 次（TW + US）
- 驗收：兩個 e2e test 全綠；`report_service.py` 覆蓋率 ≥ 85%

#### Phase 3 完成條件 (DoD)
- [ ] `run_report_pipeline()` 簽名與 G-2 一致
- [ ] `RunReportResult` 欄位齊全（G-3）
- [ ] 三步驟順序與失敗行為符合 G-4
- [ ] 結構化 log 含 `job_id` + `trigger`
- [ ] Decimal 轉換僅在 `_build_*` 邊界，全為 `Decimal(str(...))`
- [ ] `scheduler.py` 切換完成，原 `send_*_report` 已刪除
- [ ] Pipeline 單測 + 整合測試全綠
- [ ] `report_service.py` 覆蓋率 ≥ 85%

### Phase 4 — 查詢介面
13. `GET /api/v1/reports/history` 主查詢 endpoint（含三種情境分支）
14. `GET /api/v1/reports/history/options` metadata endpoint（含 Redis cache + invalidate hook）
15. Telegram `/history` 純文字 fallback handler
16. Telegram `callback_query` 處理 + inline keyboard 互動流程（type → market → symbol → period）
17. 整合測試
18. Railway 部署前置（Postgres plugin、環境變數填寫）

### Phase 5 — 手動觸發 endpoint（Phase 3 完成後）

> 結構化 log 與 `run_report_pipeline()` 已在 Phase 3 完成；本 Phase 只做 trigger endpoint 的 router 包裝。

19. `POST /api/v1/reports/history/trigger` endpoint（Bearer token 授權、`dry_run` / `skip_*` 直通 `run_report_pipeline`）
20. `tests/test_trigger_endpoint.py`（含未授權 401 / `ADMIN_TOKEN` 未設 503 / 正常 200 / `report_period` 格式錯誤 422）
21. `.env.example` / `Procfile` 對應更新

### Phase 6 — 歷史 Backfill 一次性腳本（2026-01/02/03）
22. `scripts/backfill_history.py` — CLI 參數解析 + log 設定
23. 月底持倉重建邏輯（依時序累積 transactions、計算 weighted avg_cost）
24. yfinance 歷史價抓取（含 TW random delay 1-2.5s）
25. summary 表彙總計算（pnl_delta 依月份順序）
26. 執行 dry-run → 確認 → 真實寫入；驗證 `/options` 回傳 3 個 period
27. 確認無誤後 `git rm` 移除腳本（保留 spec 紀錄即可）

每個 phase 獨立可驗證。Phase 1 通過後 Phase 2 可平行進行 repository 與 sheet_writer。

---

## 風險與提醒

1. **Alembic migration 策略**：第一版過後任何欄位變動**必須走 alembic**，禁止手動改生產表
2. **Railway Postgres 免費額度**：Hobby 方案 Postgres 預設 100 MB→1 GB；本 spec 資料量 10 年 <10 MB，遠低於上限
3. **`DATABASE_URL` 在本機 vs Railway**：Railway auto-inject，本機需自行填；`.env.example` 已加說明
4. **Sheet API Quota**：Google Sheets API 預設 300 req/min/project，本 spec 每月最多 2 次 batch write（TW + US），無風險
5. **時區**：`captured_at` 用 `TIMESTAMPTZ`，寫入時帶 Asia/Taipei tzinfo；`report_period` 字串語意沿用 spec-005
6. **Service Account 洩漏**：JSON key 只放 Railway env / 本機 `.env`（已 gitignore），**絕對不 commit**
