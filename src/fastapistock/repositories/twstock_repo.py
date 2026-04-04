"""Repository for fetching Taiwan stock data via yfinance.

Handles all external I/O: rate-respectful delays, timeouts, and
raw-data normalisation before handing off to the service layer.
"""

import logging
import math
import time
from random import SystemRandom

import pandas as pd
import yfinance as yf

from fastapistock.schemas.stock import StockData

logger = logging.getLogger(__name__)

_TW_SUFFIX = '.TW'
_HISTORY_PERIOD = '90d'  # enough for MA60 (60 trading days ≈ 3 months)
_REQUEST_TIMEOUT = 10  # seconds


class StockNotFoundError(Exception):
    """Raised when yfinance returns no data for the requested symbol."""


def _ticker_symbol(code: str) -> str:
    """Append the '.TW' suffix required by yfinance for Taiwan stocks.

    Args:
        code: Raw Taiwan stock code (e.g. '0050').

    Returns:
        yfinance-compatible symbol (e.g. '0050.TW').
    """
    code = code.strip()
    return code if code.endswith(_TW_SUFFIX) else f'{code}{_TW_SUFFIX}'


def _safe_float(value: float, fallback: float) -> float:
    """Return *value* unless it is NaN, in which case return *fallback*.

    Args:
        value: Candidate float that may be NaN.
        fallback: Value to use when *value* is not a number.

    Returns:
        A finite float.
    """
    return fallback if math.isnan(value) else value


def fetch_stock(code: str) -> StockData:
    """Fetch the latest snapshot for one Taiwan stock code.

    Applies a random polite delay before each network call to avoid
    triggering yfinance / Yahoo Finance rate limits.

    Args:
        code: Taiwan stock code (e.g. '0050', '2330').

    Returns:
        A populated StockData instance.

    Raises:
        StockNotFoundError: If yfinance returns an empty history for *code*.
    """
    sleep_s = SystemRandom().uniform(0.5, 2.0)
    logger.debug('Sleeping %.2fs before fetching %s', sleep_s, code)
    time.sleep(sleep_s)

    symbol = _ticker_symbol(code)
    logger.info('Fetching stock data for %s', symbol)

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=_HISTORY_PERIOD, timeout=_REQUEST_TIMEOUT)

    if hist.empty:
        raise StockNotFoundError(f'No data found for symbol {code!r}')

    return _build_stock_data(code, hist)


def _build_stock_data(code: str, hist: pd.DataFrame) -> StockData:
    """Convert a yfinance history DataFrame into a StockData model.

    Args:
        code: Original Taiwan stock code used as the display name.
        hist: DataFrame with columns Close and Volume, indexed by date.

    Returns:
        StockData with price, MA20, MA60, LastDayPrice, and Volume.
    """
    close = hist['Close']
    last_price = float(close.iloc[-1])

    last_day_price = float(close.iloc[-2]) if len(close) >= 2 else last_price

    raw_ma20 = float(close.rolling(20).mean().iloc[-1])
    raw_ma60 = float(close.rolling(60).mean().iloc[-1])

    ma20 = _safe_float(raw_ma20, last_price)
    ma60 = _safe_float(raw_ma60, last_price)

    volume = int(hist['Volume'].iloc[-1])

    return StockData(
        Name=code,
        price=round(last_price, 2),
        ma20=round(ma20, 2),
        ma60=round(ma60, 2),
        LastDayPrice=round(last_day_price, 2),
        Volume=volume,
    )
