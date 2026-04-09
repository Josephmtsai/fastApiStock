# 快速入門：美股分析 API + FT Monitor

## 前置作業：`.env` 新增設定

```bash
# Telegram（補充 chat ID）
TELEGRAM_CHAT_ID=6696169593

# 美股
US_STOCK_SYMBOLS=VOO,QQQ,NVDA,TSM
US_STOCK_CACHE_TTL=60

# 台股快取（抽取後）
TW_STOCK_CACHE_TTL=5

# FT Monitor（Google Sheets）
GOOGLE_SHEET_ID=<your_sheet_id>
GOOGLE_SHEET_FT_GID=<ft_summary_gid>
GOOGLE_SHEET_QUARTERLY_GID=<quarterly_gid>
FT_WATCH_SYMBOLS=TSM,NVDA,QQQ,VOO
GS_CACHE_TTL=300

# 警示閾值
FT_ALERT_BELOW_PCT_WARN=5
FT_ALERT_BELOW_PCT_CRITICAL=10
FT_ALERT_DROP_FROM_HIGH_PCT=20

# 限流（美股路由）
RATE_LIMIT_US_STOCK_WINDOW=60
RATE_LIMIT_US_STOCK_COUNT=10
RATE_LIMIT_US_STOCK_BLOCK=30
```

---

## 情境 1：查詢單一美股（含技術分析）

```bash
# 啟動伺服器
uv run uvicorn src.fastapistock.main:app --reload

# 查詢 NVDA
curl http://localhost:8000/api/v1/us-stock/NVDA
# → 200，包含 price、market_state、ta（RSI/MACD/MA/BB）、sentiment
```

---

## 情境 2：批次查詢多支美股

```bash
curl "http://localhost:8000/api/v1/us-stock?symbols=VOO,QQQ,NVDA"
# → 200，data 為包含 3 筆 USStockData 的陣列
```

---

## 情境 3：取得 FT 持倉警示

```bash
curl http://localhost:8000/api/v1/ft-monitor
# → 200，包含 holdings、alerts（空列表代表目前無警示）、quarterly_summary
```

---

## 情境 4：驗證機密值已移除

```bash
# 應回傳零比對結果
grep -rn '8141247468\|6696169593\|1RDRpwuXjHHU9nr1BYPk_k6fzRO_lnhnmwrBLws3oHjg' sample/ src/
```

---

## 情境 5：執行測試

```bash
uv run pytest tests/test_us_stock.py tests/test_ft_monitor.py -v
uv run pytest -q  # 全部測試
```

---

## 情境 6：靜態檢查

```bash
uv run ruff check . --fix && uv run ruff format .
uv run mypy src/
```
