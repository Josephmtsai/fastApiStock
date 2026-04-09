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

from fastapistock.schemas.stock import RichStockData, StockData
from fastapistock.services import indicators as ind_svc

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
    sleep_s = SystemRandom().uniform(0.1, 0.5)
    logger.info('Sleeping %.2fs before fetching %s', sleep_s, code)
    time.sleep(sleep_s)

    symbol = _ticker_symbol(code)
    logger.info('Fetching history for %s (period=%s)', symbol, _HISTORY_PERIOD)

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=_HISTORY_PERIOD, timeout=_REQUEST_TIMEOUT)
    logger.info('History fetched for %s: %d rows', symbol, len(hist))

    if hist.empty:
        raise StockNotFoundError(f'No data found for symbol {code!r}')

    logger.info('Fetching ticker.info for %s', symbol)
    info = ticker.info
    chinese_name: str = info.get('longName') or info.get('shortName') or code
    logger.info('ticker.info done for %s — name=%s', symbol, chinese_name)
    return _build_stock_data(code, hist, chinese_name)


def fetch_tw_rich_stock(code: str) -> RichStockData:
    """Fetch a Taiwan stock's full technical-analysis snapshot.

    Applies a random polite delay before the network call. Fetches 6 months
    of history to support MA50 and MACD calculations.

    Args:
        code: Taiwan stock code (e.g. '0050', '2330').

    Returns:
        Populated RichStockData instance with all available indicators.

    Raises:
        StockNotFoundError: If yfinance returns an empty history for *code*.
    """
    sleep_s = SystemRandom().uniform(0.1, 0.5)
    logger.info('Sleeping %.2fs before fetching rich TW %s', sleep_s, code)
    time.sleep(sleep_s)

    symbol = _ticker_symbol(code)
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period='6mo', timeout=_REQUEST_TIMEOUT)
    logger.info('Rich history for %s: %d rows', symbol, len(hist))

    if hist.empty:
        raise StockNotFoundError(f'No data found for symbol {code!r}')

    info = ticker.info
    display_name: str = info.get('longName') or info.get('shortName') or code

    close = hist['Close']
    last_price = round(float(close.iloc[-1]), 2)
    prev_close = round(float(close.iloc[-2]), 2) if len(close) >= 2 else last_price
    change = round(last_price - prev_close, 2)
    change_pct = round((change / prev_close * 100) if prev_close else 0.0, 2)

    result = ind_svc.calculate(hist)
    return RichStockData(
        symbol=code,
        display_name=display_name,
        market='TW',
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


def _build_stock_data(
    code: str, hist: pd.DataFrame, chinese_name: str = ''
) -> StockData:
    """Convert a yfinance history DataFrame into a StockData model.

    Args:
        code: Original Taiwan stock code used as the display name.
        hist: DataFrame with columns Close and Volume, indexed by date.
        chinese_name: Chinese display name fetched from ticker.info.

    Returns:
        StockData with price, MA20, MA60, LastDayPrice, Volume, and ChineseName.
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
        ChineseName=chinese_name,
        price=round(last_price, 2),
        ma20=round(ma20, 2),
        ma60=round(ma60, 2),
        LastDayPrice=round(last_day_price, 2),
        Volume=volume,
    )
