# 合約：美股查詢 API

**消費端**：API 客戶端 / Telegram 排程器
**提供端**：FastAPI 應用

---

## 單一股票查詢

```
GET /api/v1/us-stock/{symbol}
```

### 成功回應（200）

```json
{
  "status": "success",
  "data": {
    "symbol": "NVDA",
    "price": 875.30,
    "prev_close": 862.00,
    "change": 13.30,
    "change_pct": 1.54,
    "market_state": "REGULAR",
    "price_label": "即時",
    "ta": {
      "rsi": 62.5,
      "macd": 4.21,
      "macd_signal": 3.88,
      "macd_hist": 0.33,
      "ma20": 840.50,
      "ma50": 810.20,
      "ma200": 650.10,
      "bb_upper": 920.00,
      "bb_mid": 840.50,
      "bb_lower": 761.00,
      "vol_today": 35000000,
      "vol_avg20": 42000000,
      "w52h": 974.00,
      "w52l": 410.00
    },
    "sentiment": {
      "score": 3,
      "verdict": "看漲",
      "summary": "偏看漲 (評分 3/8)",
      "bull_reasons": ["站上 MA20 短期均線，趨勢向上", "MACD 柱狀轉正（金叉），動能翻多"],
      "bear_reasons": ["RSI=62.5 偏超買，動能可能減弱"]
    }
  },
  "message": ""
}
```

### 錯誤回應

| 條件 | HTTP | 回應 |
|------|------|------|
| 代碼不存在 | 404 | `{"status":"error","data":null,"message":"Symbol ZZZZ not found"}` |
| Yahoo Finance 不可用 | 503 | `{"status":"error","data":null,"message":"Unable to fetch quote for NVDA"}` |

---

## 批次查詢

```
GET /api/v1/us-stock?symbols=VOO,QQQ,NVDA
```

### 成功回應（200）

```json
{
  "status": "success",
  "data": [ /* USStockData 陣列，順序與 symbols 參數一致 */ ],
  "message": ""
}
```

### 市場狀態說明

| `market_state` 值 | `price_label` | 說明 |
|------------------|--------------|------|
| `PRE` / `PREPRE` | 盤前 | 盤前交易時段 |
| `REGULAR` | 即時 | 正常交易時段 |
| `POST` / `POSTPOST` | 盤後 | 盤後交易時段 |
| `CLOSED` | 收盤 | 休市 |
