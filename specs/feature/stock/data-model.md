# 資料模型：美股分析 API + 設定變數抽取

**第 1 階段產出**

---

## 新增 Pydantic Schema（`src/fastapistock/schemas/us_stock.py`）

### TechnicalAnalysis（技術指標）

```python
class TechnicalAnalysis(BaseModel):
    rsi: float | None = None          # RSI(14)
    macd: float | None = None         # MACD 線
    macd_signal: float | None = None  # 訊號線
    macd_hist: float | None = None    # 柱狀圖
    ma20: float | None = None
    ma50: float | None = None         # 資料不足 50 筆時為 None
    ma200: float | None = None        # 資料不足 200 筆時為 None
    bb_upper: float | None = None     # 布林上軌（20期，2σ）
    bb_mid: float | None = None
    bb_lower: float | None = None
    vol_today: int | None = None      # 今日成交量
    vol_avg20: int | None = None      # 20 日均量
    w52h: float | None = None         # 52 週高點
    w52l: float | None = None         # 52 週低點
```

### SentimentScore（情緒評分）

```python
class SentimentScore(BaseModel):
    score: int                  # −8 到 +8
    verdict: str                # "看漲" | "中性觀望" | "看跌"
    summary: str                # 例："強烈看漲 (評分 5/8)"
    bull_reasons: list[str]     # 看多訊號說明
    bear_reasons: list[str]     # 看空訊號說明
```

### USStockData（美股完整資料）

```python
class USStockData(BaseModel):
    symbol: str
    price: float
    prev_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    market_state: str           # PRE | REGULAR | POST | POSTPOST | CLOSED
    price_label: str            # "盤前" | "即時" | "盤後" | "收盤"
    ta: TechnicalAnalysis
    sentiment: SentimentScore | None = None
```

---

## 新增 Pydantic Schema（`src/fastapistock/schemas/ft_monitor.py`）

### FTBuySuggestion（買入建議）

```python
class FTBuySuggestion(BaseModel):
    label: str   # 例："立即買入（現價）"
    price: float
```

### FTAlert（警示）

```python
class FTAlert(BaseModel):
    alert_type: str             # BELOW_AVG_5 | BELOW_AVG_10 | ABOVE_AVG_BUT_DOWN_FROM_HIGH
    level: str                  # "緊急" | "注意" | "回調機會"
    message: str
    buy_suggestions: list[FTBuySuggestion]
```

### FTHolding（持倉）

```python
class FTHolding(BaseModel):
    symbol: str
    avg_cost: float
    shares: float
    highest: float | None = None        # 試算表記錄的最高買入價
    current_price: float | None = None
    diff_from_avg_pct: float | None = None
```

### QuarterlyProgress（季度進度）

```python
class QuarterlyProgress(BaseModel):
    symbol: str
    target: float
    actual: float
    achieve_rate: float         # 0.0 – 1.0
    achieved: bool
    remaining_days: int
```

### QuarterlySummary（季度摘要）

```python
class QuarterlySummary(BaseModel):
    period_start: str           # ISO 日期字串
    period_end: str
    total_days: int
    elapsed_days: int
    time_progress_pct: float
    items: list[QuarterlyProgress]
    overall_actual: float
    overall_target: float
    overall_pct: float
```

### FTMonitorResult（ft-monitor 回應主體）

```python
class FTMonitorResult(BaseModel):
    holdings: list[FTHolding]
    alerts: dict[str, list[FTAlert]]    # symbol → 警示清單
    quarterly_summary: QuarterlySummary | None = None
```

---

## `config.py` 新增設定

```python
# Telegram（補充）
TELEGRAM_CHAT_ID: str = os.getenv('TELEGRAM_CHAT_ID', '')      # 原本硬編碼在 sample/

# 美股
US_STOCK_SYMBOLS: list[str] = _csv_list('US_STOCK_SYMBOLS', 'VOO,QQQ,NVDA,TSM')
US_STOCK_CACHE_TTL: int = int(os.getenv('US_STOCK_CACHE_TTL', '60'))

# 台股快取（抽取原本的魔法數字）
TW_STOCK_CACHE_TTL: int = int(os.getenv('TW_STOCK_CACHE_TTL', '5'))

# FT Monitor
GOOGLE_SHEET_ID: str = os.getenv('GOOGLE_SHEET_ID', '')
GOOGLE_SHEET_FT_GID: str = os.getenv('GOOGLE_SHEET_FT_GID', '')
GOOGLE_SHEET_QUARTERLY_GID: str = os.getenv('GOOGLE_SHEET_QUARTERLY_GID', '')
FT_WATCH_SYMBOLS: list[str] = _csv_list('FT_WATCH_SYMBOLS', 'TSM,NVDA,QQQ,VOO')
GS_CACHE_TTL: int = int(os.getenv('GS_CACHE_TTL', '300'))
FT_ALERT_BELOW_PCT_WARN: float = float(os.getenv('FT_ALERT_BELOW_PCT_WARN', '5'))
FT_ALERT_BELOW_PCT_CRITICAL: float = float(os.getenv('FT_ALERT_BELOW_PCT_CRITICAL', '10'))
FT_ALERT_DROP_FROM_HIGH_PCT: float = float(os.getenv('FT_ALERT_DROP_FROM_HIGH_PCT', '20'))

# 輔助函式（私有）
def _csv_list(key: str, default: str) -> list[str]:
    return [v.strip() for v in os.getenv(key, default).split(',') if v.strip()]
```

---

## 新增 Repository 結構

```
repositories/
├── twstock_repo.py          （現有，不變）
├── us_stock_repo.py         新增 — Yahoo v7/v8 HTTP + crumb session singleton
└── google_sheets_repo.py    新增 — 抓取 FT Summary 與 Quarterly CSV
```

## 新增 Service 結構

```
services/
├── stock_service.py         修改 — 改用 TW_STOCK_CACHE_TTL from config
├── technical_analysis.py    新增 — calc_rsi, calc_macd, calc_bollinger, calc_ta, sentiment_score
├── us_stock_service.py      新增 — get_us_stock(), get_us_stocks() + Redis 快取
└── ft_monitor_service.py    新增 — 整合 Google Sheets + 美股報價 + 警示邏輯
```

---

## Redis 快取 Key 設計

| Key 格式 | TTL | 內容 |
|---------|-----|------|
| `us-stock:{SYMBOL}:{date}` | `US_STOCK_CACHE_TTL`（60s） | 序列化的 `USStockData` |
| `ft-monitor:holdings:{date}` | `GS_CACHE_TTL`（300s） | Google Sheets FT Summary 解析結果 |
| `ft-monitor:quarterly:{date}` | `GS_CACHE_TTL`（300s） | Google Sheets Quarterly 解析結果 |
| `stock:{CODE}:{date}` | `TW_STOCK_CACHE_TTL`（5s） | 台股快取（現有，key 格式不變） |
