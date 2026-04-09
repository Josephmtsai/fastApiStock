# Phase 1 Data Model：定時股票推播排程

## 1. Schema：RichStockData

位置：`src/fastapistock/schemas/stock.py`（新增於現有 `StockData` 之後）

```python
from pydantic import BaseModel

class RichStockData(BaseModel):
    """技術分析完整快照，供排程推播使用。

    Attributes:
        symbol: 股票代碼（台股如 '0050'，美股如 'AAPL'）。
        display_name: 顯示名稱（公司名或中文名）。
        market: 市場別，'TW' 或 'US'。
        price: 最新價格。
        prev_close: 前一交易日收盤價。
        change: 漲跌金額（price - prev_close）。
        change_pct: 漲跌幅（百分比）。
        ma20: 20 日移動平均。
        ma50: 50 日移動平均，歷史不足時為 None。
        rsi: RSI(14)，歷史不足時為 None。
        macd: MACD 線值，歷史不足時為 None。
        macd_signal: MACD 訊號線，歷史不足時為 None。
        macd_hist: MACD 柱狀值（macd - macd_signal），歷史不足時為 None。
        bb_upper: 布林通道上軌，歷史不足時為 None。
        bb_mid: 布林通道中線（MA20），歷史不足時為 None。
        bb_lower: 布林通道下軌，歷史不足時為 None。
        volume: 最新交易日成交量。
        volume_avg20: 20 日平均成交量。
        week52_high: 近 6 個月最高價（作為 52 週區間的代理指標）。
        week52_low: 近 6 個月最低價。
        premarket_price: 美股盤前價格（來自 yfinance info.preMarketPrice）；
            台股或非盤前時段為 None。
    """

    symbol: str
    display_name: str
    market: Literal['TW', 'US']
    price: float
    prev_close: float
    change: float
    change_pct: float
    ma20: float
    ma50: float | None = None
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    bb_upper: float | None = None
    bb_mid: float | None = None
    bb_lower: float | None = None
    volume: int
    volume_avg20: int
    week52_high: float | None = None
    week52_low: float | None = None
    premarket_price: float | None = None
```

> **現有 `StockData` 不受影響**，API endpoint 繼續使用原本的 schema。

---

## 2. Config 新增欄位

位置：`src/fastapistock/config.py`

```python
# 新增（讀自環境變數）
TELEGRAM_USER_ID: str = os.getenv('TELEGRAM_USER_ID', '')

def tw_stock_codes() -> list[str]:
    """解析 TW_STOCKS 環境變數為股票代碼清單。"""
    raw = os.getenv('TW_STOCKS', '')
    return [c.strip() for c in raw.split(',') if c.strip()]

def us_stock_symbols() -> list[str]:
    """解析 US_STOCKS 環境變數為股票代碼清單。"""
    raw = os.getenv('US_STOCKS', '')
    return [s.strip().upper() for s in raw.split(',') if s.strip()]
```

---

## 3. Repository：US Stock

位置：`src/fastapistock/repositories/us_stock_repo.py`

**主要函式簽名**：

```python
def fetch_us_stock(symbol: str) -> RichStockData:
    """抓取單支美股的完整技術分析快照。

    Args:
        symbol: 美股 ticker（如 'AAPL'、'TSLA'）。

    Returns:
        填充完整的 RichStockData 實例。

    Raises:
        StockNotFoundError: yfinance 回傳空資料時拋出。
    """
```

**內部流程**：
1. random sleep (0.1–0.5 s)
2. `yf.Ticker(symbol).history(period='6mo', timeout=10)`
3. 檢查是否為空 → 拋出 `StockNotFoundError`
4. 取 `fast_info.last_price` 作為現價（fallback 到 `Close.iloc[-1]`）
5. 呼叫 `indicators.calculate(hist)` 計算技術指標
6. 回傳 `RichStockData`

---

## 4. Repository：TW Rich Stock（新增）

位置：`src/fastapistock/repositories/twstock_repo.py`（新增函式，不改現有）

新增：
```python
def fetch_tw_rich_stock(code: str) -> RichStockData:
    """抓取單支台股的完整技術分析快照（供排程使用）。"""
```

> 現有 `fetch_stock()` 回傳 `StockData`，保持不動。
> 新函式回傳 `RichStockData`，共用底層 yfinance 呼叫邏輯。

---

## 5. Service：Indicators

位置：`src/fastapistock/services/indicators.py`

所有技術指標計算集中於此，純函數設計（接收 DataFrame，回傳 dict）：

```python
from dataclasses import dataclass
import pandas as pd

@dataclass(frozen=True)
class IndicatorResult:
    """技術指標計算結果。"""
    rsi: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    ma20: float | None
    ma50: float | None
    bb_upper: float | None
    bb_mid: float | None
    bb_lower: float | None
    volume_avg20: int
    week52_high: float | None
    week52_low: float | None

def calculate(hist: pd.DataFrame) -> IndicatorResult:
    """從 yfinance history DataFrame 計算所有技術指標。

    Args:
        hist: yfinance history DataFrame（含 Close, Volume, High, Low 欄位）。

    Returns:
        IndicatorResult，歷史不足時相關欄位為 None。
    """
```

**評分函式**：

```python
@dataclass(frozen=True)
class ScoreResult:
    score: int            # -8 ~ +8
    verdict: str          # '看漲' | '看跌' | '中性觀望'
    bull_reasons: list[str]
    bear_reasons: list[str]

def score_stock(price: float, change_pct: float, indicators: IndicatorResult) -> ScoreResult:
    """根據技術指標計算綜合評分與判斷。"""
```

評分規則：

| 指標 | 看漲 | 看跌 |
|------|------|------|
| RSI < 30 | +2 | — |
| RSI 30–40 | +1 | — |
| RSI > 70 | — | -2 |
| RSI 60–70 | — | -1 |
| MACD hist > 0 且 MACD > 0 | +2 | — |
| MACD hist > 0 | +1 | — |
| MACD hist < 0 且 MACD < 0 | — | -2 |
| MACD hist < 0 | — | -1 |
| 現價 > MA20 | +1 | — |
| 現價 < MA20 | — | -1 |
| 現價 > MA50 | +1 | — |
| 現價 < MA50 | — | -1 |
| BB 位置 < 15% | +1 | — |
| BB 位置 > 85% | — | -1 |
| 放量上漲 (>1.5x) | +1 | — |
| 放量下跌 (>1.5x) | — | -1 |

判斷：score ≥ +3 → 看漲，≤ -3 → 看跌，其餘 → 中性觀望

---

## 6. Service：Scheduler Push

位置：`src/fastapistock/services/scheduler_push.py`

```python
async def push_tw_stocks() -> None:
    """抓取台股資料並推播到 Telegram。"""

async def push_us_stocks() -> None:
    """抓取美股資料並推播到 Telegram。"""
```

---

## 7. Service：Rich Telegram Formatter

位置：`src/fastapistock/services/telegram_service.py`（新增函式）

```python
def format_rich_stock_message(
    stocks: list[RichStockData],
    market: Literal['TW', 'US'],
    now: datetime,
) -> str:
    """建立包含技術指標的 Telegram MarkdownV2 訊息。

    Args:
        stocks: 股票清單。
        market: 市場別，決定 header 和幣別標示。
        now: 推播時間（Asia/Taipei）。

    Returns:
        MarkdownV2 格式的訊息字串。
    """

def send_rich_stock_message(user_id: str, stocks: list[RichStockData], market: Literal['TW', 'US']) -> bool:
    """送出技術分析格式的 Telegram 訊息。"""
```

---

## 8. Router：台股手動推播（升級現有）

位置：`src/fastapistock/routers/telegram.py`（修改現有 router）

現有 `send_telegram_stock_info()` 改為呼叫 `get_rich_tw_stocks()` 並使用
`send_rich_stock_message()`，API 介面（path、query params、response envelope）不變。

```python
@router.get('/{id}', response_model=ResponseEnvelope[None])
async def send_telegram_stock_info(
    id: str,
    stock: str = Query(default='', description='Comma-separated Taiwan stock codes'),
) -> ResponseEnvelope[None]:
    """Fetch rich TW stock data and push MarkdownV2 message to a Telegram user."""
    # codes 過濾邏輯不變（isdigit()）
    # 改呼叫 get_rich_tw_stocks(codes)
    # 改呼叫 send_rich_stock_message(id, stocks, market='TW')
```

## 9. Router：美股手動推播（新增）

位置：`src/fastapistock/routers/us_telegram.py`（新建）

```python
router = APIRouter(prefix='/api/v1/usMessage', tags=['us-telegram'])

@router.get(
    '/{id}',
    response_model=ResponseEnvelope[None],
    summary='Push US stock info to a Telegram user',
)
async def send_us_telegram_stock_info(
    id: str,
    stock: str = Query(default='', description='Comma-separated US stock tickers'),
) -> ResponseEnvelope[None]:
    """Fetch rich US stock data and push MarkdownV2 message to a Telegram user.

    Non-alpha stock tickers in *stock* are silently ignored.
    Tickers are uppercased automatically.

    Args:
        id: Telegram user/chat ID to push the message to.
        stock: Comma-separated US stock tickers (e.g. 'AAPL,TSLA').

    Returns:
        ResponseEnvelope with status 'success' when the message is sent,
        or 'error' with a descriptive message otherwise.
    """
    # 解析 ticker，去空白，轉大寫，過濾非字母
    symbols = [s.strip().upper() for s in stock.split(',')
               if s.strip() and s.strip().isalpha()]
    if not symbols:
        return ResponseEnvelope(status='error', message='No valid stock tickers provided')
    ...
```

## 10. Service：Rich TW Stocks（新增）

位置：`src/fastapistock/services/stock_service.py`（新增函式，現有不動）

```python
def get_rich_tw_stock(code: str) -> RichStockData:
    """Cache-first lookup for a single TW stock with full indicators."""

def get_rich_tw_stocks(codes: list[str]) -> list[RichStockData]:
    """Parallel cache-first fetch for multiple TW stocks with full indicators."""
```

Cache key 格式：`rich_tw:{code}:{date}` 與現有 `stock:{code}:{date}` 不衝突。

## 11. Service：US Stocks（新增）

位置：`src/fastapistock/services/us_stock_service.py`（新建）

```python
def get_us_stock(symbol: str) -> RichStockData:
    """Cache-first lookup for a single US stock with full indicators."""

def get_us_stocks(symbols: list[str]) -> list[RichStockData]:
    """Parallel cache-first fetch for multiple US stocks with full indicators."""
```

Cache key 格式：`us_stock:{symbol}:{date}`

> **`get_us_stocks` 與 `get_rich_tw_stocks` 被排程器和 API endpoint 共同呼叫**，
> 這是唯一實作，不重複。

## 12. Scheduler 模組

位置：`src/fastapistock/scheduler.py`

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo

_TZ = ZoneInfo('Asia/Taipei')

def is_tw_market_window(now: datetime) -> bool:
    """判斷現在是否在台股推播時間窗口。"""

def is_us_market_window(now: datetime) -> bool:
    """判斷現在是否在美股推播時間窗口。"""

async def _scheduled_push() -> None:
    """每 30 分鐘觸發，依時間窗口決定推送台股或美股。"""

def build_scheduler() -> AsyncIOScheduler:
    """建立並設定 APScheduler，回傳已設定但未啟動的 scheduler。"""
```

---

## 9. Main Lifespan 修改

位置：`src/fastapistock/main.py`

```python
from contextlib import asynccontextmanager
from fastapistock.scheduler import build_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = build_scheduler()
    scheduler.start()
    logger.info('APScheduler started')
    yield
    scheduler.shutdown(wait=False)
    logger.info('APScheduler stopped')

# create_app() 加入 lifespan=lifespan
```

---

## 13. 狀態流程圖

```
FastAPI startup (lifespan)
└── build_scheduler() → AsyncIOScheduler.start()
    └── 每 30 分鐘觸發 _scheduled_push()
        ├── is_tw_market_window(now)?
        │   └── YES → push_tw_stocks()
        │       └── get_rich_tw_stocks(TW_STOCKS)  ← 共用 service
        └── is_us_market_window(now)?
            └── YES → push_us_stocks()
                └── get_us_stocks(US_STOCKS)       ← 共用 service

HTTP API（手動觸發）
├── GET /api/v1/tgMessage/{id}?stock=0050,2330
│   └── get_rich_tw_stocks(codes)               ← 同一 service
│       → send_rich_stock_message(id, 'TW')
└── GET /api/v1/usMessage/{id}?stock=AAPL,NVDA
    └── get_us_stocks(symbols)                  ← 同一 service
        → send_rich_stock_message(id, 'US')

共用底層
├── get_rich_tw_stocks() / get_us_stocks()
│   ├── Redis cache hit → RichStockData
│   └── cache miss → fetch_tw_rich_stock() / fetch_us_stock()
│       → indicators.calculate(hist)
│       → Redis.put(key, data, TTL=300)
└── send_rich_stock_message()
    ├── format_rich_stock_message() → MarkdownV2 str
    └── httpx.post(Telegram API)

FastAPI shutdown (lifespan)
└── scheduler.shutdown()
```
