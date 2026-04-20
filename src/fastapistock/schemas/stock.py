"""Pydantic schemas for the stock domain."""

from typing import Literal

from pydantic import BaseModel


class StockData(BaseModel):
    """Real-time stock snapshot returned by GET /api/v1/stock/{id}.

    Attributes:
        Name: Taiwan stock code (e.g. '0050', '2330').
        ChineseName: Chinese display name of the stock (e.g. '元大台灣50').
        price: Latest closing price in TWD.
        ma20: 20-day (monthly) moving average of close prices.
        ma60: 60-day (quarterly) moving average of close prices.
        LastDayPrice: Previous trading day's closing price in TWD.
        Volume: Trading volume of the latest trading day.
    """

    Name: str
    ChineseName: str = ''
    price: float
    ma20: float
    ma60: float
    LastDayPrice: float
    Volume: int


class RichStockData(BaseModel):
    """Full technical-analysis snapshot used by the scheduler and rich API endpoints.

    Attributes:
        symbol: Ticker symbol (e.g. '0050' for TW, 'AAPL' for US).
        display_name: Human-readable company name.
        market: Market identifier; 'TW' for Taiwan, 'US' for US equities.
        price: Latest closing price.
        prev_close: Previous trading day closing price.
        change: Price change (price - prev_close).
        change_pct: Percentage change relative to prev_close.
        ma20: 20-day simple moving average.
        ma50: 50-day simple moving average; None when history is insufficient.
        rsi: RSI(14); None when history is insufficient.
        macd: MACD line value; None when history is insufficient.
        macd_signal: MACD signal line; None when history is insufficient.
        macd_hist: MACD histogram (macd - signal); None when history is insufficient.
        bb_upper: Bollinger upper band (20,2); None when history is insufficient.
        bb_mid: Bollinger middle band (MA20); None when history is insufficient.
        bb_lower: Bollinger lower band (20,2); None when history is insufficient.
        volume: Latest trading day volume.
        volume_avg20: 20-day average volume.
        week52_high: Highest price in available history (proxy for 52-week high).
        week52_low: Lowest price in available history (proxy for 52-week low).
        premarket_price: US pre-market price; None for TW or outside pre-market hours.
        price_date: ISO-8601 date of the price data ('YYYY-MM-DD'); today when sourced
            from fast_info (real-time), last trading day when sourced from history.
        avg_cost: Average cost per share (portfolio); None when stock not held.
        unrealized_pnl: Unrealized profit/loss in TWD; None when not held.
        shares: Number of shares held; None when not held.
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
    price_date: str | None = None
    avg_cost: float | None = None
    unrealized_pnl: float | None = None
    shares: int | None = None
