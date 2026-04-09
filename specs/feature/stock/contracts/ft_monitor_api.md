# 合約：FT 持倉監控 API

**消費端**：API 客戶端 / Telegram 排程器
**提供端**：FastAPI 應用

---

## 端點

```
GET /api/v1/ft-monitor
```

---

## 成功回應（200）

```json
{
  "status": "success",
  "data": {
    "holdings": [
      {
        "symbol": "NVDA",
        "avg_cost": 650.00,
        "shares": 10.0,
        "highest": 874.00,
        "current_price": 875.30,
        "diff_from_avg_pct": 34.66
      }
    ],
    "alerts": {
      "VOO": [
        {
          "alert_type": "BELOW_AVG_5",
          "level": "注意",
          "message": "現價低於均價 6.2%（均價 $480.00）",
          "buy_suggestions": [
            { "label": "試探買入", "price": 450.00 },
            { "label": "理想買入", "price": 456.00 },
            { "label": "深度加碼", "price": 432.00 }
          ]
        }
      ]
    },
    "quarterly_summary": {
      "period_start": "2026-01-01",
      "period_end": "2026-03-31",
      "total_days": 90,
      "elapsed_days": 45,
      "time_progress_pct": 50.0,
      "items": [
        {
          "symbol": "NVDA",
          "target": 5000.0,
          "actual": 3200.0,
          "achieve_rate": 0.64,
          "achieved": false,
          "remaining_days": 45
        }
      ],
      "overall_actual": 12000.0,
      "overall_target": 20000.0,
      "overall_pct": 60.0
    }
  },
  "message": ""
}
```

---

## 警示類型說明

| `alert_type` | 觸發條件 | 預設閾值 |
|-------------|---------|---------|
| `BELOW_AVG_5` | 現價 < 均價 × (1 − `FT_ALERT_BELOW_PCT_WARN`%) | 5% |
| `BELOW_AVG_10` | 現價 < 均價 × (1 − `FT_ALERT_BELOW_PCT_CRITICAL`%) | 10% |
| `ABOVE_AVG_BUT_DOWN_FROM_HIGH` | 現價 > 均價，但距最高點回落 ≥ `FT_ALERT_DROP_FROM_HIGH_PCT`% | 20% |

---

## 錯誤回應

| 條件 | HTTP | 回應 |
|------|------|------|
| Google Sheets 不可用且無快取 | 503 | `{"status":"error","data":null,"message":"Google Sheets unavailable"}` |
| 美股報價抓取失敗 | 503 | `{"status":"error","data":null,"message":"Unable to fetch current prices"}` |
