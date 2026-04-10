# Quickstart: Telegram Bot Webhook with Command Menu & Quarterly Investment Achievement Rate

**Branch**: `003-bot-webhook-commands` | **Date**: 2026-04-10

---

## 環境變數（新增）

在 `.env` 加入以下兩個新變數：

```dotenv
# 季度投資計畫 Sheet 的 GID（tab ID）
GOOGLE_SHEETS_INVESTMENT_PLAN_GID=1192950573

# Telegram Webhook 驗證 Secret（1–256 字元，限 A-Z a-z 0-9 _ -）
TELEGRAM_WEBHOOK_SECRET=your-random-secret-here
```

> 現有變數（`GOOGLE_SHEETS_ID`, `TELEGRAM_TOKEN`, `TELEGRAM_USER_ID`, `PORTFOLIO_CACHE_TTL`, `REDIS_*`）不需更動。

---

## 啟動應用程式

```bash
# 一般開發啟動
uv run uvicorn fastapistock.main:app --reload

# 啟動時會自動呼叫 setMyCommands，Telegram 指令選單即生效
```

---

## 設定 Telegram Webhook（部署後執行一次）

```bash
# 替換 {TOKEN} 與 {DOMAIN} 為實際值
curl -X POST "https://api.telegram.org/bot{TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://{DOMAIN}/api/v1/webhook/telegram",
    "secret_token": "your-random-secret-here"
  }'

# 確認設定成功
curl "https://api.telegram.org/bot{TOKEN}/getWebhookInfo"
```

---

## 執行測試

```bash
# 單元測試
uv run pytest tests/unit/test_investment_plan_repo.py -v
uv run pytest tests/unit/test_investment_plan_service.py -v

# 整合測試（需要 Redis 與網路）
uv run pytest tests/integration/test_webhook.py -v

# 全部測試 + 覆蓋率
uv run pytest --cov=fastapistock --cov-report=term-missing
```

---

## 本地測試 Webhook（不需要 ngrok）

```bash
# 模擬 Telegram 推送 /q 指令
curl -X POST "http://localhost:8000/api/v1/webhook/telegram" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: your-random-secret-here" \
  -d '{
    "update_id": 1,
    "message": {
      "message_id": 1,
      "from": {"id": 你的TELEGRAM_USER_ID, "is_bot": false, "first_name": "Test"},
      "chat": {"id": 你的TELEGRAM_USER_ID},
      "text": "/q"
    }
  }'

# 模擬 /help
curl -X POST "http://localhost:8000/api/v1/webhook/telegram" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: your-random-secret-here" \
  -d '{
    "update_id": 2,
    "message": {
      "message_id": 2,
      "from": {"id": 你的TELEGRAM_USER_ID, "is_bot": false, "first_name": "Test"},
      "chat": {"id": 你的TELEGRAM_USER_ID},
      "text": "/help"
    }
  }'
```

---

## 驗證 Google Sheets 欄位對應

確認 GID `1192950573` 的 Sheet 格式如下（第 1 列為標題列，從第 2 列開始讀取）：

| A（股票代號）| B（開始日期）| C（結束日期）| ... | F（預期 USD）| G（已投入 USD）|
|------------|-----------|-----------|-----|------------|--------------|
| AAPL | 2026-04-01 | 2026-06-30 | | 1,000 | 500 |
| TSLA | 2026-04-01 | 2026-06-30 | | 500 | 250 |

---

## Code Review 前置作業

```bash
# Ruff lint + format
uv run ruff check . --fix && uv run ruff format .

# Type check
uv run mypy src/

# Pre-commit hooks
uv run pre-commit run --all-files
```
