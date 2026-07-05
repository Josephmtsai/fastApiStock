# API Contract: Telegram Webhook Endpoint

**Branch**: `003-bot-webhook-commands` | **Date**: 2026-04-10

---

## POST /api/v1/webhook/telegram

Telegram Bot API 回呼端點。Telegram 在用戶傳送訊息時主動呼叫此端點。

### Request

**Headers**

| Header | Required | Description |
|--------|----------|-------------|
| `X-Telegram-Bot-Api-Secret-Token` | ✅ 必填 | 與 `TELEGRAM_WEBHOOK_SECRET` 環境變數比對 |
| `Content-Type` | ✅ 必填 | `application/json` |

**Body**（Telegram 標準 Update 格式）

```json
{
  "update_id": 123456789,
  "message": {
    "message_id": 1,
    "from": {
      "id": 987654321,
      "is_bot": false,
      "first_name": "Joseph"
    },
    "chat": {
      "id": 987654321
    },
    "text": "/q"
  }
}
```

### Response

所有情境均回傳 HTTP 200（Telegram 要求）。

**Success（處理成功或靜默忽略）**

```json
{
  "status": "success",
  "data": null,
  "message": "ok"
}
```

**Error（secret token 驗證失敗）**

HTTP 403

```json
{
  "status": "error",
  "data": null,
  "message": "Invalid webhook secret"
}
```

---

## 指令行為對照表

| 收到文字 | 處理方式 | Bot 回覆內容 |
|---------|---------|------------|
| `/q` | 查詢當季投資計畫，計算達成率 | 達成率報告（見下方格式）|
| `/us AAPL,TSLA` | 查詢美股報價 | 現有 `format_rich_stock_message` 格式 |
| `/us`（無參數）| 參數不足 | 使用說明文字 |
| `/tw 0050,2330` | 查詢台股報價 | 現有 `format_rich_stock_message` 格式 |
| `/tw`（無參數）| 參數不足 | 使用說明文字 |
| `/help` | 列出所有指令 | 指令選單文字 |
| 其他文字 | 靜默忽略 | 不回應 |
| 非授權 user_id | 靜默忽略 | 不回應 |

---

## Bot 回覆格式

### `/q` 達成率報告

```
📊 本季投資達成率

整體：▓▓▓▓▓▓▓░░░ 72.50%
已投入：$1,450.00 / 預期：$2,000.00 USD

📌 個股明細：
  AAPL  ▓▓▓▓▓▓▓▓▓░  90.00%  ($900/$1,000)
  TSLA  ▓▓▓▓▓░░░░░  50.00%  ($250/$500)
  NVDA  ▓▓▓░░░░░░░  30.00%  ($150/$500)

期間：2026-04-01 ~ 2026-06-30
```

個股 expected=0 時，該行顯示：
```
  AAPL  N/A  ($500/$0)
```

無當季資料時：
```
本季無投資計畫資料
```

預期金額為 0 時：
```
本季預期投資金額為 0，無法計算達成率
```

### `/help` 指令選單

```
📋 可用指令

/q — 本季投資達成率
/us AAPL,TSLA — 美股即時報價
/tw 0050,2330 — 台股即時報價
/help — 顯示此說明
```

### `/us` 無參數

```
用法：/us AAPL,TSLA
請提供至少一個美股代號（以逗號分隔）
```

### `/tw` 無參數

```
用法：/tw 0050,2330
請提供至少一個台股代號（以逗號分隔）
```

---

## 進度條格式

`rate_pct` 轉換為 10 格進度條：

```python
filled = round(rate_pct / 10)          # 0–10
bar = '▓' * filled + '░' * (10 - filled)
```

---

## 設定 Webhook（一次性手動操作）

部署後執行一次：

```bash
curl -X POST "https://api.telegram.org/bot{TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://<your-domain>/api/v1/webhook/telegram",
    "secret_token": "<TELEGRAM_WEBHOOK_SECRET 的值>"
  }'
```

---

## Rate Limiting

Webhook 端點套用獨立的 Rate Limit 設定（env prefix `WEBHOOK`）：

| 環境變數 | 預設值 | 說明 |
|---------|-------|------|
| `RATE_LIMIT_WEBHOOK_WINDOW` | 60 | 滑動視窗秒數 |
| `RATE_LIMIT_WEBHOOK_COUNT` | 60 | 視窗內最大請求數 |
| `RATE_LIMIT_WEBHOOK_BLOCK` | 60 | 封鎖持續秒數 |

> Telegram 每秒最多推送 1 次，正常情況不會觸發 Rate Limit。
