# Data Model: Telegram Bot Webhook with Command Menu & Quarterly Investment Achievement Rate

**Date**: 2026-04-10 | **Branch**: `003-bot-webhook-commands`

---

## 實體一覽

### 1. `InvestmentPlanEntry`（dataclass, frozen）

> 位置：`src/fastapistock/repositories/investment_plan_repo.py`

| 欄位 | 型別 | Sheet 欄 | 說明 |
|------|------|----------|------|
| `symbol` | `str` | A (index 0) | 股票代號（原始字串，不做正規化）|
| `start_date` | `datetime.date` | B (index 1) | 季度開始日期 |
| `end_date` | `datetime.date` | C (index 2) | 季度結束日期 |
| `expected_usd` | `float` | F (index 5) | 預期投資金額（USD），空白視為 0.0 |
| `invested_usd` | `float` | G (index 6) | 已投入金額（USD），空白視為 0.0 |

**驗證規則**：
- `start_date` ≤ `end_date`（解析失敗的行整行跳過）
- `expected_usd` 和 `invested_usd` 均 ≥ 0

---

### 2. `SymbolAchievement`（dataclass, frozen）

> 位置：`src/fastapistock/services/investment_plan_service.py`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `symbol` | `str` | 股票代號 |
| `rate_pct` | `float` | 個股達成率（invested / expected × 100）；expected=0 時為 -1.0 |
| `invested_usd` | `float` | 已投入金額（USD）|
| `expected_usd` | `float` | 預期金額（USD）|

---

### 3. `QuarterlyAchievementReport`（dataclass, frozen）

> 位置：`src/fastapistock/services/investment_plan_service.py`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `rate_pct` | `float` | 整體達成率百分比（Σ invested / Σ expected × 100）|
| `total_invested` | `float` | 當季已投入合計（USD）|
| `total_expected` | `float` | 當季預期投入合計（USD）|
| `symbols` | `list[str]` | 當季匹配的股票代號列表（保持相容性）|
| `per_symbol` | `list[SymbolAchievement]` | 個股達成率明細，順序與 symbols 一致 |
| `date_range` | `str` | 顯示用字串，例：`2026-04-01 ~ 2026-06-30` |

**計算公式**：
```
篩選條件：entry.start_date <= today <= entry.end_date
         且 (entry.expected_usd > 0 或 entry.invested_usd > 0)

# 整體
rate_pct = sum(invested_usd) / sum(expected_usd) × 100

# 個股
symbol_rate_pct = entry.invested_usd / entry.expected_usd × 100
                  （entry.expected_usd == 0 時設為 -1.0）
```

**邊界情況**：
- `total_expected == 0`：`rate_pct` 設為 `-1.0`（哨兵值），service 層轉換為錯誤訊息
- 無匹配行：回傳 `None`，router 層轉換為「無資料」訊息
- 個股 `expected_usd == 0`：該個股 `rate_pct` 設為 `-1.0`，格式化時顯示 `N/A`

---

### 3. Telegram Webhook Payload（Pydantic models）

> 位置：`src/fastapistock/routers/webhook.py`（或獨立 schemas 檔案）

#### `TelegramFrom`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | `int` | Telegram 用戶 ID |
| `is_bot` | `bool` | 是否為 Bot |
| `first_name` | `str` | 用戶名稱（顯示用）|

#### `TelegramChat`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | `int` | Chat ID（用於回覆訊息）|

#### `TelegramMessage`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `message_id` | `int` | 訊息 ID |
| `from_` | `TelegramFrom \| None` | 發送者（Field alias: `from`）|
| `chat` | `TelegramChat` | 聊天對象 |
| `text` | `str \| None` | 訊息文字（非文字訊息時為 None）|

#### `TelegramUpdate`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `update_id` | `int` | Telegram 更新唯一 ID |
| `message` | `TelegramMessage \| None` | 一般訊息（callback_query 等其他類型忽略）|

---

## 模組關係圖

```
routers/webhook.py
    │
    ├── 解析 TelegramUpdate（Pydantic）
    ├── 驗證 user_id == TELEGRAM_USER_ID
    │
    ├── /q   → services/investment_plan_service.py
    │               → repositories/investment_plan_repo.py
    │               → cache/redis_cache.py
    │
    ├── /us  → services/us_stock_service.py（現有）
    ├── /tw  → services/stock_service.py（現有）
    │
    ├── /help → 靜態文字回覆
    │
    └── 所有回覆 → services/telegram_service.reply_to_chat()（新增 helper）
```

---

## Cache 資料格式

Redis key：`investment_plan:{YYYY-MM-DD}`（以查詢當天日期為 key）

儲存格式（JSON list of dicts）：
```json
[
  {
    "symbol": "AAPL",
    "start_date": "2026-04-01",
    "end_date": "2026-06-30",
    "expected_usd": 1000.0,
    "invested_usd": 500.0
  }
]
```

TTL：`PORTFOLIO_CACHE_TTL`（預設 3600 秒）

---

## 狀態轉換

```
TelegramUpdate 到達
    │
    ▼
secret token 驗證
    ├── FAIL → HTTP 403（不記錄訊息內容）
    └── PASS
         │
         ▼
    user_id 驗證
         ├── FAIL → HTTP 200（靜默忽略，Telegram 需要收到 200）
         └── PASS
              │
              ▼
         command dispatch
              ├── /q     → 查詢 → 計算 → 回覆
              ├── /us    → 查詢 → 回覆
              ├── /tw    → 查詢 → 回覆
              ├── /help  → 靜態回覆
              └── 其他  → HTTP 200（靜默忽略）
```

> **注意**：Telegram 要求 webhook endpoint 必須回傳 HTTP 200，否則 Telegram 會重試推送。
> 所有靜默忽略情境（非授權用戶、未知指令）均回傳 HTTP 200 + `ResponseEnvelope(status='success')`。
