# Contract：API Endpoint 規範

## 現有 Endpoint 升級

### GET /api/v1/tgMessage/{id}

**異動類型**：訊息格式升級（不破壞 API 介面）

| 項目 | 現在 | 升級後 |
|------|------|--------|
| Path | `/api/v1/tgMessage/{id}` | 不變 |
| Query | `?stock=0050,2330` | 不變 |
| Response body | `ResponseEnvelope[None]` | 不變 |
| Telegram 格式 | 純文字（舊 `send_stock_message`） | MarkdownV2 富格式（`send_rich_stock_message`） |
| 資料模型 | `StockData` | `RichStockData` |

**Request**：
```
GET /api/v1/tgMessage/123456789?stock=0050,2330,2454
```

**Response（成功）**：
```json
{
  "status": "success",
  "data": null,
  "message": "Message sent to 123456789"
}
```

**Response（錯誤）**：
```json
{
  "status": "error",
  "data": null,
  "message": "No valid stock codes provided"
}
```

**錯誤情境**：
| 情況 | message |
|------|---------|
| `stock` 為空或全部非數字 | `No valid stock codes provided` |
| yfinance 查無資料 | `No data found for symbol '9999'` |
| Telegram 發送失敗 | `Failed to send Telegram message` |

---

## 新增 Endpoint

### GET /api/v1/usMessage/{id}

**位置**：`src/fastapistock/routers/us_telegram.py`
**Tags**：`us-telegram`
**Rate Limiting**：全局 middleware 套用，與其他 endpoint 一致

**Path Parameters**：

| 參數 | 型別 | 說明 |
|------|------|------|
| `id` | `str` | Telegram chat/user ID |

**Query Parameters**：

| 參數 | 型別 | 說明 | 範例 |
|------|------|------|------|
| `stock` | `str` | 逗號分隔美股 ticker | `AAPL,TSLA,NVDA` |

**Ticker 過濾規則**：
- 去除前後空白
- 轉大寫
- 過濾非純英文字母的 token（`s.isalpha()` 為 False 者靜默忽略）

**Request**：
```
GET /api/v1/usMessage/123456789?stock=AAPL,TSLA,nvda
```
（`nvda` 自動轉為 `NVDA`）

**Response（成功）**：
```json
{
  "status": "success",
  "data": null,
  "message": "Message sent to 123456789"
}
```

**Response（錯誤）**：
```json
{
  "status": "error",
  "data": null,
  "message": "No valid stock tickers provided"
}
```

**錯誤情境**：
| 情況 | message |
|------|---------|
| `stock` 為空或全部過濾掉 | `No valid stock tickers provided` |
| yfinance 查無資料 | `No data found for symbol 'INVALID'` |
| Telegram 發送失敗 | `Failed to send Telegram message` |

---

## Rate Limiting 說明

兩個 endpoint 皆受現有全局 `_RateLimitMiddleware` 保護。
不為個別 endpoint 新增獨立 rate limit config，沿用現有 middleware 設計。

## OpenAPI 文件

FastAPI 自動產生，可透過 `/docs` 瀏覽。
新增 endpoint 加入 `us-telegram` tag，與現有 `telegram` tag 分開顯示。
