"""Repository for fetching US stock data via yfinance.

Mirrors twstock_repo but uses ticker symbols directly (no .TW suffix),
and builds RichStockData with full technical indicators.
"""

import logging
import time
from datetime import datetime
from datetime import time as dt_time
from random import SystemRandom
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from fastapistock.config import PREMARKET_MAX_RETRIES, PREMARKET_RETRY_BASE_SLEEP
from fastapistock.repositories.twstock_repo import StockNotFoundError
from fastapistock.schemas.stock import RichStockData
from fastapistock.services import indicators as ind_svc

logger = logging.getLogger(__name__)

_HISTORY_PERIOD = '6mo'
_REQUEST_TIMEOUT = 10
_ET_TZ = ZoneInfo('America/New_York')
_PREMARKET_START = dt_time(4, 0)
_PREMARKET_END = dt_time(9, 30)


def _attempt_premarket_fetch(ticker: yf.Ticker) -> float | None:
    """Execute one yfinance 1-minute history call and extract the pre-market close.

    Args:
        ticker: An initialised yfinance Ticker instance.

    Returns:
        Rounded pre-market close price on success.

    Raises:
        ValueError: When the returned DataFrame is empty (treated as retryable).
        Exception: Propagates any yfinance network or parsing error (retryable).
    """
    hist: pd.DataFrame = ticker.history(
        period='1d',
        interval='1m',
        prepost=True,
        timeout=_REQUEST_TIMEOUT,
    )
    if hist.empty:
        raise ValueError('Empty pre-market history')

    hist.index = hist.index.tz_convert(_ET_TZ)
    times = hist.index.time  # numpy.ndarray of datetime.time objects
    mask = pd.array(
        [_PREMARKET_START <= t < _PREMARKET_END for t in times],
        dtype='boolean',
    )
    premarket = hist[mask]
    if premarket.empty:
        return None

    return round(float(premarket['Close'].iloc[-1]), 2)


def _fetch_premarket_price(ticker: yf.Ticker) -> float | None:
    """Fetch the latest pre-market close price for a US ticker with retry.

    Returns None immediately when the wall-clock (Eastern Time) is outside
    04:00–09:30, preventing historical pre-market candles from being
    misreported as a live pre-market price after the regular session opens.

    On transient failures (empty DataFrame or network exception) the function
    retries up to PREMARKET_MAX_RETRIES times with exponential backoff
    (base sleep PREMARKET_RETRY_BASE_SLEEP, doubles each attempt).

    Args:
        ticker: An initialised yfinance Ticker instance.

    Returns:
        Rounded pre-market close price, or None when all attempts fail or
        the current ET time is outside the pre-market window.
    """
    now_et = datetime.now(_ET_TZ).time()
    if not (_PREMARKET_START <= now_et < _PREMARKET_END):
        return None

    attempt = 0
    sleep_s = PREMARKET_RETRY_BASE_SLEEP
    while attempt <= PREMARKET_MAX_RETRIES:
        try:
            return _attempt_premarket_fetch(ticker)
        except Exception as exc:
            logger.warning(
                'Pre-market fetch attempt %d/%d failed: %s',
                attempt + 1,
                PREMARKET_MAX_RETRIES + 1,
                exc,
            )
            attempt += 1
            if attempt <= PREMARKET_MAX_RETRIES:
                time.sleep(sleep_s)
                sleep_s *= 2
    return None


def fetch_us_stock(symbol: str) -> RichStockData:
    """Fetch the latest technical-analysis snapshot for one US stock symbol.

    Applies a random polite delay before each network call to avoid
    triggering yfinance / Yahoo Finance rate limits.

    Args:
        symbol: US stock ticker in uppercase (e.g. 'AAPL', 'TSLA').

    Returns:
        A populated RichStockData instance with market='US'.

    Raises:
        StockNotFoundError: If yfinance returns an empty history for *symbol*.
    """
    sleep_s = SystemRandom().uniform(0.1, 0.5)
    logger.info('Sleeping %.2fs before fetching US %s', sleep_s, symbol)
    time.sleep(sleep_s)

    logger.info('Fetching history for US %s (period=%s)', symbol, _HISTORY_PERIOD)
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=_HISTORY_PERIOD, timeout=_REQUEST_TIMEOUT)
    logger.info('History fetched for %s: %d rows', symbol, len(hist))

    if hist.empty:
        raise StockNotFoundError(f'No data found for symbol {symbol!r}')

    info = ticker.info
    display_name: str = info.get('longName') or info.get('shortName') or symbol
    premarket_price: float | None = _fetch_premarket_price(ticker)

    close = hist['Close']
    last_price = round(float(close.iloc[-1]), 2)
    prev_close = round(float(close.iloc[-2]), 2) if len(close) >= 2 else last_price
    change = round(last_price - prev_close, 2)
    change_pct = round((change / prev_close * 100) if prev_close else 0.0, 2)

    result = ind_svc.calculate(hist)
    return RichStockData(
        symbol=symbol,
        display_name=display_name,
        market='US',
        price=last_price,
        prev_close=prev_close,
        change=change,
        change_pct=change_pct,
        ma20=result.ma20 or round(last_price, 2),
        ma50=result.ma50,
        rsi=result.rsi,
        macd=result.macd,
        macd_signal=result.macd_signal,
        macd_hist=result.macd_hist,
        bb_upper=result.bb_upper,
        bb_mid=result.bb_mid,
        bb_lower=result.bb_lower,
        volume=result.volume_today,
        volume_avg20=result.volume_avg20,
        week52_high=result.week52_high,
        week52_low=result.week52_low,
        premarket_price=premarket_price,
    )
