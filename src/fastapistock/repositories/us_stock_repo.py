"""Repository for fetching US stock data via yfinance.

Mirrors twstock_repo but uses ticker symbols directly (no .TW suffix),
and builds RichStockData with full technical indicators.
"""

import logging
import time
from random import SystemRandom

import yfinance as yf

from fastapistock.repositories.twstock_repo import StockNotFoundError
from fastapistock.schemas.stock import RichStockData
from fastapistock.services import indicators as ind_svc

logger = logging.getLogger(__name__)

_HISTORY_PERIOD = '6mo'
_REQUEST_TIMEOUT = 10


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
    )
