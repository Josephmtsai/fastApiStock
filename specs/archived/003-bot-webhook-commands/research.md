# Research: Telegram Bot Webhook with Command Menu & Quarterly Investment Achievement Rate

**Date**: 2026-04-10 | **Branch**: `003-bot-webhook-commands`

---

## 1. Telegram Webhook 設定機制

**Decision**: 使用 Telegram Bot API 的 `setWebhook` 方法，在應用程式部署後手動執行一次（非啟動時自動呼叫）。

**Rationale**:
- `setWebhook` 呼叫應只執行一次；每次 app 重啟都觸發會造成不必要的 API 呼叫。
- 推薦做法：部署後手動 curl 執行，或做成 management 指令（`python -m fastapistock.scripts.setup_webhook`）。
- Webhook URL 格式：`https://<your-domain>/api/v1/webhook/telegram`

**Alternatives considered**:
- 在 `lifespan` startup 呼叫 `setWebhook`：簡單但每次重啟都呼叫 API，且如果 URL 尚未就緒會失敗。選擇排除。
- 使用 polling（`getUpdates`）：不需要 webhook，但不適合生產環境（需要長輪詢連線）。選擇排除。

---

## 2. Telegram setMyCommands（指令選單）

**Decision**: 在 `_lifespan` startup 中呼叫 `setMyCommands`，讓 Bot 在 Telegram 介面顯示指令自動補全選單。

**Rationale**:
- `setMyCommands` 是冪等操作（重複呼叫不會造成副作用），適合在 startup 執行。
- 使用者在 Telegram 輸入 `/` 時會看到可用指令列表。

**呼叫方式**：

```
POST https://api.telegram.org/bot{TOKEN}/setMyCommands
Body:
{
  "commands": [
    {"command": "q",    "description": "本季投資達成率"},
    {"command": "us",   "description": "美股報價，例：/us AAPL,TSLA"},
    {"command": "tw",   "description": "台股報價，例：/tw 0050,2330"},
    {"command": "help", "description": "顯示所有指令說明"}
  ]
}
```

**Alternatives considered**:
- 手動一次性執行：可行，但每次新增指令都需要手動操作。選擇排除。

---

## 3. Webhook Secret Token 驗證

**Decision**: 透過 `X-Telegram-Bot-Api-Secret-Token` 請求 Header 驗證，值從環境變數 `TELEGRAM_WEBHOOK_SECRET` 讀取。

**Rationale**:
- Telegram 在設定 webhook 時可指定 `secret_token` 參數，之後每次推送都會帶上此 Header。
- 驗證流程：若 Header 值與 `TELEGRAM_WEBHOOK_SECRET` 不符，立即回應 HTTP 403 並記錄 warning log。
- Secret token 要求：1–256 字元，僅允許 `A-Z`, `a-z`, `0-9`, `_`, `-`。

**實作細節**：
```python
secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
if secret != config.TELEGRAM_WEBHOOK_SECRET:
    raise HTTPException(status_code=403, detail='Invalid webhook secret')
```

**Alternatives considered**:
- IP 白名單（Telegram IP range）：維護成本高，Telegram IP 可能變動。選擇排除。
- 無驗證：安全性風險，任何人知道 URL 即可偽造請求。選擇排除。

---

## 4. Google Sheets 欄位對應（GID 1192950573）

**Decision**: 使用與現有 `portfolio_repo.py` 相同的 CSV 匯出方式，欄位 index 如下：

| Column | Index | 用途 |
|--------|-------|------|
| A | 0 | 股票代號 |
| B | 1 | 開始日期（YYYY-MM-DD 或 YYYY/MM/DD）|
| C | 2 | 結束日期 |
| F | 5 | 預期投資額（USD）|
| G | 6 | 已投入金額（USD）|

**日期解析**：使用 `datetime.strptime` 嘗試多種格式（`%Y-%m-%d`, `%Y/%m/%d`），解析失敗則跳過該行並記錄 warning。

**數字解析**：沿用 `portfolio_repo._parse_number()` 邏輯（去除千位分隔符）；欄位為空時返回 `0.0`。

**Rationale**: 複用現有模式，不引入新的 HTTP 客戶端或 Google API SDK。

**Alternatives considered**:
- Google Sheets API v4（帶 OAuth）：功能強大但認證複雜，此場景只需讀取公開 Sheet，CSV 匯出已足夠。選擇排除。

---

## 5. Redis Cache Key 命名規範

**Decision**: 使用 `investment_plan:{YYYY-MM-DD}` 作為 cache key，TTL 使用 `PORTFOLIO_CACHE_TTL`（預設 3600 秒）。

**Rationale**:
- 日期作為 key 的一部分，確保隔天的快取不會影響當天計算。
- 與現有 `stock:` 前綴模式保持一致命名風格。
- 使用現有 `redis_cache.get()` / `redis_cache.put()` 介面，不重新發明快取機制（Constitution IV）。

**Cache 資料格式**：將 `list[dict]` 序列化為 JSON 存入 Redis（redis_cache 已支援 `dict` 存取）。

**Fallback**：Redis 不可用時（RedisError），直接進行 live fetch，不拋出錯誤。

**Alternatives considered**:
- 不加日期（`investment_plan`）：快取永遠存在，每天的資料可能不更新。選擇排除。
- 用 YYYYMM（月份）：季度資料按月快取過於細緻，按日快取剛好。

---

## 6. 指令 Dispatch 設計

**Decision**: 在 `webhook.py` router 內做 command dispatch，以 `if/elif` 鏈處理最多 4 個指令；業務邏輯委派至 service 層。

**Message text 解析規則**：
- 取 `message.text` 的第一個 token（以空白分隔）作為 command（去除 `@bot_name` 後綴）
- 剩餘部分作為 arguments 傳給 service
- 非 `/` 開頭的訊息：忽略（不回應）

**Alternatives considered**:
- Command Handler 類別／Plugin 架構：4 個指令不需要這樣的複雜度（YAGNI）。選擇排除。
- python-telegram-bot 套件：引入新依賴，現有 httpx 已可滿足需求。選擇排除。

---

## 7. 達成率計算邊界情況

| 狀況 | 處理方式 |
|------|---------|
| 無當季資料（無任何行的日期包含今天）| 回覆「本季無投資計畫資料」|
| 分母（Σ F）為 0 | 回覆「本季預期投資金額為 0，無法計算達成率」|
| 某行 F 或 G 為空白/無效 | 跳過該行，記錄 warning log |
| 日期格式無法解析 | 跳過該行，記錄 warning log |
| 達成率 > 100%（超額投入）| 正常顯示，不做限制 |
