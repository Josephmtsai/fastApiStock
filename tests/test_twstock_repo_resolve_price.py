"""Unit tests for twstock_repo._resolve_price() and RichStockData.price_date field.

Covers:
- fast_info.last_price valid  → uses fast_info data, price_date = today
- fast_info.last_price is None → fallback to hist close
- fast_info.last_price is NaN  → fallback to hist close
- fast_info entirely absent (AttributeError) → fallback to hist close
- prev_close fallback when fast_info.previous_close is NaN
- RichStockData has price_date field and accepts str | None
"""

import math
from datetime import date, datetime

import pandas as pd
import pytest

from fastapistock.repositories.twstock_repo import _resolve_price
from fastapistock.schemas.stock import RichStockData

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hist(closes: list[float], ref_date: str = '2025-03-14') -> pd.DataFrame:
    """Build a minimal history DataFrame with the given Close prices.

    The last date in the index will be *ref_date* so price_date assertions are
    deterministic.
    """
    n = len(closes)
    index = pd.bdate_range(end=ref_date, periods=n)
    return pd.DataFrame({'Close': closes}, index=index)


class _FastInfo:
    """Minimal stub for yfinance Ticker.fast_info."""

    def __init__(self, last_price: float | None, previous_close: float | None) -> None:
        self.last_price = last_price
        self.previous_close = previous_close


class _TickerStub:
    """Minimal stub for yfinance Ticker that exposes fast_info as a real property."""

    def __init__(
        self,
        last_price: float | None = None,
        previous_close: float | None = None,
        raise_attr_error: bool = False,
    ) -> None:
        self._raise = raise_attr_error
        self._fast_info = _FastInfo(last_price, previous_close)

    @property
    def fast_info(self) -> _FastInfo:
        if self._raise:
            raise AttributeError('fast_info not available')
        return self._fast_info


def _make_ticker(
    last_price: float | None,
    previous_close: float | None = None,
    raise_attr_error: bool = False,
) -> '_TickerStub':
    """Return a stub that mimics a yfinance Ticker with fast_info."""
    return _TickerStub(
        last_price=last_price,
        previous_close=previous_close,
        raise_attr_error=raise_attr_error,
    )


# ---------------------------------------------------------------------------
# Tests: fast_info path
# ---------------------------------------------------------------------------


class TestResolvePriceFastInfoUsed:
    """_resolve_price uses fast_info when last_price is a valid float."""

    def test_valid_last_price_returned(self) -> None:
        # Arrange
        hist = _make_hist([190.0, 195.0])
        close = hist['Close']
        ticker = _make_ticker(last_price=200.5, previous_close=195.0)

        # Act
        last_price, prev_close, price_date = _resolve_price(ticker, close, hist)

        # Assert
        assert last_price == pytest.approx(200.5, rel=1e-6)

    def test_valid_previous_close_returned_from_fast_info(self) -> None:
        # Arrange
        hist = _make_hist([190.0, 195.0])
        close = hist['Close']
        ticker = _make_ticker(last_price=200.5, previous_close=195.0)

        # Act
        _, prev_close, _ = _resolve_price(ticker, close, hist)

        # Assert – fast_info.previous_close takes priority over hist
        assert prev_close == pytest.approx(195.0, rel=1e-6)

    def test_price_date_is_today_when_fast_info_used(self) -> None:
        # Arrange
        hist = _make_hist([190.0, 195.0])
        close = hist['Close']
        ticker = _make_ticker(last_price=200.5, previous_close=195.0)

        # Act
        _, _, price_date = _resolve_price(ticker, close, hist)

        # Assert
        assert price_date == date.today().isoformat()

    def test_prev_close_falls_back_to_hist_when_fast_info_prev_is_nan(self) -> None:
        # Arrange – previous_close is NaN; should fall back to last close in hist
        hist = _make_hist([190.0, 195.0])
        close = hist['Close']
        ticker = _make_ticker(last_price=200.5, previous_close=float('nan'))

        # Act
        _, prev_close, _ = _resolve_price(ticker, close, hist)

        # Assert – hist close.iloc[-1] = 195.0 is used as fallback
        assert prev_close == pytest.approx(195.0, rel=1e-6)

    def test_prev_close_falls_back_to_last_price_when_hist_empty(self) -> None:
        # Arrange – only one row in hist, previous_close is NaN
        hist = _make_hist([200.5])
        close = hist['Close']
        ticker = _make_ticker(last_price=200.5, previous_close=float('nan'))

        # Act
        _, prev_close, _ = _resolve_price(ticker, close, hist)

        # Assert – single-row fallback: prev_close == last_price
        assert prev_close == pytest.approx(200.5, rel=1e-6)

    def test_result_prices_are_rounded_to_two_decimal_places(self) -> None:
        # Arrange
        hist = _make_hist([190.123, 195.456])
        close = hist['Close']
        ticker = _make_ticker(last_price=200.9999, previous_close=195.1111)

        # Act
        last_price, prev_close, _ = _resolve_price(ticker, close, hist)

        # Assert
        assert last_price == round(200.9999, 2)
        assert prev_close == round(195.1111, 2)


# ---------------------------------------------------------------------------
# Tests: fallback path – last_price is None
# ---------------------------------------------------------------------------


class TestResolvePriceFallbackOnNone:
    """_resolve_price falls back to hist when fast_info.last_price is None."""

    def test_last_price_from_hist_when_fast_info_none(self) -> None:
        # Arrange
        hist = _make_hist([190.0, 195.0], ref_date='2025-03-14')
        close = hist['Close']
        ticker = _make_ticker(last_price=None)

        # Act
        last_price, _, _ = _resolve_price(ticker, close, hist)

        # Assert – hist.Close.iloc[-1] = 195.0
        assert last_price == pytest.approx(195.0, rel=1e-6)

    def test_prev_close_from_hist_when_fast_info_none(self) -> None:
        # Arrange
        hist = _make_hist([190.0, 195.0], ref_date='2025-03-14')
        close = hist['Close']
        ticker = _make_ticker(last_price=None)

        # Act
        _, prev_close, _ = _resolve_price(ticker, close, hist)

        # Assert – hist.Close.iloc[-2] = 190.0
        assert prev_close == pytest.approx(190.0, rel=1e-6)

    def test_price_date_is_hist_date_string_when_fast_info_none(self) -> None:
        # Arrange
        hist = _make_hist([190.0, 195.0], ref_date='2025-03-14')
        close = hist['Close']
        ticker = _make_ticker(last_price=None)

        # Act
        _, _, price_date = _resolve_price(ticker, close, hist)

        # Assert – last index date in %Y-%m-%d
        expected = hist.index[-1].strftime('%Y-%m-%d')
        assert price_date == expected

    def test_single_row_hist_prev_equals_last_when_fast_info_none(self) -> None:
        # Arrange – only one close row available
        hist = _make_hist([195.0], ref_date='2025-03-14')
        close = hist['Close']
        ticker = _make_ticker(last_price=None)

        # Act
        last_price, prev_close, _ = _resolve_price(ticker, close, hist)

        # Assert – prev_close mirrors last_price when len(close) < 2
        assert prev_close == pytest.approx(last_price, rel=1e-6)


# ---------------------------------------------------------------------------
# Tests: fallback path – last_price is NaN
# ---------------------------------------------------------------------------


class TestResolvePriceFallbackOnNaN:
    """_resolve_price falls back to hist when fast_info.last_price is NaN."""

    def test_last_price_from_hist_when_fast_info_nan(self) -> None:
        # Arrange
        hist = _make_hist([190.0, 195.0], ref_date='2025-03-14')
        close = hist['Close']
        ticker = _make_ticker(last_price=float('nan'))

        # Act
        last_price, _, _ = _resolve_price(ticker, close, hist)

        # Assert
        assert not math.isnan(last_price)
        assert last_price == pytest.approx(195.0, rel=1e-6)

    def test_prev_close_from_hist_when_fast_info_nan(self) -> None:
        # Arrange
        hist = _make_hist([190.0, 195.0], ref_date='2025-03-14')
        close = hist['Close']
        ticker = _make_ticker(last_price=float('nan'))

        # Act
        _, prev_close, _ = _resolve_price(ticker, close, hist)

        # Assert
        assert prev_close == pytest.approx(190.0, rel=1e-6)

    def test_price_date_is_hist_date_string_when_fast_info_nan(self) -> None:
        # Arrange
        hist = _make_hist([190.0, 195.0], ref_date='2025-03-14')
        close = hist['Close']
        ticker = _make_ticker(last_price=float('nan'))

        # Act
        _, _, price_date = _resolve_price(ticker, close, hist)

        # Assert
        expected = hist.index[-1].strftime('%Y-%m-%d')
        assert price_date == expected


# ---------------------------------------------------------------------------
# Tests: fallback path – fast_info raises AttributeError
# ---------------------------------------------------------------------------


class TestResolvePriceFallbackOnAttributeError:
    """_resolve_price falls back gracefully when fast_info is unavailable."""

    def test_last_price_from_hist_when_no_fast_info(self) -> None:
        # Arrange
        hist = _make_hist([190.0, 195.0], ref_date='2025-03-14')
        close = hist['Close']
        ticker = _make_ticker(last_price=None, raise_attr_error=True)

        # Act – must not raise
        last_price, _, _ = _resolve_price(ticker, close, hist)

        # Assert
        assert last_price == pytest.approx(195.0, rel=1e-6)

    def test_prev_close_from_hist_when_no_fast_info(self) -> None:
        # Arrange
        hist = _make_hist([190.0, 195.0], ref_date='2025-03-14')
        close = hist['Close']
        ticker = _make_ticker(last_price=None, raise_attr_error=True)

        # Act
        _, prev_close, _ = _resolve_price(ticker, close, hist)

        # Assert
        assert prev_close == pytest.approx(190.0, rel=1e-6)

    def test_price_date_is_hist_date_when_no_fast_info(self) -> None:
        # Arrange
        hist = _make_hist([190.0, 195.0], ref_date='2025-03-14')
        close = hist['Close']
        ticker = _make_ticker(last_price=None, raise_attr_error=True)

        # Act
        _, _, price_date = _resolve_price(ticker, close, hist)

        # Assert
        expected = hist.index[-1].strftime('%Y-%m-%d')
        assert price_date == expected


# ---------------------------------------------------------------------------
# Tests: RichStockData schema – price_date field
# ---------------------------------------------------------------------------


class TestRichStockDataPriceDate:
    """RichStockData.price_date is present and typed str | None."""

    def _make_rich(self, **overrides: object) -> RichStockData:
        defaults: dict[str, object] = dict(
            symbol='0050',
            display_name='元大台灣50',
            market='TW',
            price=195.5,
            prev_close=193.2,
            change=2.3,
            change_pct=1.19,
            ma20=190.0,
            volume=5_000_000,
            volume_avg20=4_000_000,
        )
        defaults.update(overrides)
        return RichStockData(**defaults)  # type: ignore[arg-type]

    def test_price_date_defaults_to_none(self) -> None:
        # Arrange & Act
        stock = self._make_rich()

        # Assert
        assert stock.price_date is None

    def test_price_date_accepts_iso_date_string(self) -> None:
        # Arrange & Act
        stock = self._make_rich(price_date='2025-03-14')

        # Assert
        assert stock.price_date == '2025-03-14'

    def test_price_date_accepts_today_isoformat(self) -> None:
        # Arrange
        today = date.today().isoformat()

        # Act
        stock = self._make_rich(price_date=today)

        # Assert
        assert stock.price_date == today

    def test_price_date_accepts_none_explicitly(self) -> None:
        # Arrange & Act
        stock = self._make_rich(price_date=None)

        # Assert
        assert stock.price_date is None

    def test_price_date_field_present_in_model_fields(self) -> None:
        # Verify the field exists on the model schema (not just on an instance)
        assert 'price_date' in RichStockData.model_fields

    def test_model_serialises_price_date(self) -> None:
        # Arrange
        stock = self._make_rich(price_date='2025-03-14')

        # Act
        data = stock.model_dump()

        # Assert
        assert data['price_date'] == '2025-03-14'

    def test_model_serialises_none_price_date(self) -> None:
        # Arrange
        stock = self._make_rich(price_date=None)

        # Act
        data = stock.model_dump()

        # Assert
        assert data['price_date'] is None


# ---------------------------------------------------------------------------
# Tests: telegram_service label change
# ---------------------------------------------------------------------------


class TestTelegramServiceLabel:
    """_format_stock_message uses '最後成交:' instead of '現價:'."""

    def test_last_trade_label_in_plain_message(self) -> None:
        from fastapistock.schemas.stock import StockData
        from fastapistock.services.telegram_service import _format_stock_message

        # Arrange
        stock = StockData(
            Name='0050',
            ChineseName='元大台灣50',
            price=195.5,
            ma20=190.0,
            ma60=185.0,
            LastDayPrice=193.2,
            Volume=5_000_000,
        )

        # Act
        msg = _format_stock_message([stock])

        # Assert – new label present
        assert '最後成交:' in msg
        # Assert – old label absent
        assert '現價:' not in msg

    def test_last_trade_label_in_rich_block(self) -> None:
        from zoneinfo import ZoneInfo

        from fastapistock.services.telegram_service import format_rich_stock_message

        # Arrange
        stock = RichStockData(
            symbol='0050',
            display_name='元大台灣50',
            market='TW',
            price=195.5,
            prev_close=193.2,
            change=2.3,
            change_pct=1.19,
            ma20=190.0,
            volume=5_000_000,
            volume_avg20=4_000_000,
        )
        now = datetime(2025, 3, 14, 9, 0, tzinfo=ZoneInfo('Asia/Taipei'))

        # Act
        msg = format_rich_stock_message([stock], 'TW', now)

        # Assert – rich block also uses '最後成交:'
        assert '最後成交:' in msg
        assert '現價:' not in msg
