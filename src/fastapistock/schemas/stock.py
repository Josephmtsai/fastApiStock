"""Pydantic schemas for the stock domain."""

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
