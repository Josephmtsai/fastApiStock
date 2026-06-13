"""Tests for the US stock repository."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from fastapistock.repositories.twstock_repo import StockNotFoundError
from fastapistock.repositories.us_stock_repo import (
    _fetch_premarket_price,
    fetch_us_stock,
)
from fastapistock.schemas.stock import RichStockData

_ET = ZoneInfo('America/New_York')

# Freeze the wall-clock inside _fetch_premarket_price for deterministic tests.
_PATCH_DATETIME = 'fastapistock.repositories.us_stock_repo.datetime'
_PREMARKET_NOW = datetime(2025, 1, 2, 4, 30, 0, tzinfo=_ET)  # 04:30 ET — inside window
_POSTMARKET_NOW = datetime(2025, 1, 2, 10, 0, 0, tzinfo=_ET)  # 10:00 ET — after open


def _make_hist(n: int = 60, price: float = 150.0) -> pd.DataFrame:
    prices = [price] * n
    return pd.DataFrame(
        {
            'Open': prices,
            'High': [p * 1.01 for p in prices],
            'Low': [p * 0.99 for p in prices],
            'Close': prices,
            'Volume': [50_000_000] * n,
        },
        index=pd.date_range(start=date(2025, 1, 1), periods=n, freq='B'),
    )


def _make_premarket_hist(close: float = 185.5) -> pd.DataFrame:
    """Build a 1-minute DataFrame with one row in ET pre-market (04:30 ET).

    2025-01-02 is in Eastern Standard Time (UTC-5).
    04:30 ET = 09:30 UTC.
    """
    idx = pd.DatetimeIndex(
        ['2025-01-02 09:30:00'],
        tz=UTC,
    ).tz_convert(_ET)
    return pd.DataFrame(
        {
            'Open': [close],
            'High': [close],
            'Low': [close],
            'Close': [close],
            'Volume': [100_000],
        },
        index=idx,
    )


def _make_ticker_mock(
    daily_hist: pd.DataFrame,
    premarket_hist: pd.DataFrame | None = None,
    info: dict[str, object] | None = None,
) -> MagicMock:
    """Return a Ticker mock whose .history() returns correct data per call."""
    mock = MagicMock()
    mock.info = info or {}
    empty = pd.DataFrame()

    def _history_side_effect(**kwargs: object) -> pd.DataFrame:
        if kwargs.get('prepost') is True:
            return premarket_hist if premarket_hist is not None else empty
        return daily_hist

    mock.history.side_effect = _history_side_effect
    return mock


# ---------------------------------------------------------------------------
# _fetch_premarket_price unit tests
# ---------------------------------------------------------------------------


@patch(_PATCH_DATETIME)
def test_fetch_premarket_price_returns_value_during_premarket(
    mock_dt: MagicMock,
) -> None:
    mock_dt.now.return_value = _PREMARKET_NOW
    ticker = MagicMock()
    ticker.history.return_value = _make_premarket_hist(185.5)
    result = _fetch_premarket_price(ticker)
    assert result == pytest.approx(185.5, rel=0.001)


@patch('fastapistock.repositories.us_stock_repo.time.sleep')
@patch(_PATCH_DATETIME)
def test_fetch_premarket_price_returns_none_on_empty_hist(
    mock_dt: MagicMock,
    _mock_sleep: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'fastapistock.repositories.us_stock_repo.PREMARKET_MAX_RETRIES', 0
    )
    mock_dt.now.return_value = _PREMARKET_NOW
    ticker = MagicMock()
    ticker.history.return_value = pd.DataFrame()
    assert _fetch_premarket_price(ticker) is None


@patch(_PATCH_DATETIME)
def test_fetch_premarket_price_returns_none_when_no_premarket_rows(
    mock_dt: MagicMock,
) -> None:
    """Rows outside 04:00–09:30 ET in the data should yield None."""
    mock_dt.now.return_value = _PREMARKET_NOW
    idx = pd.DatetimeIndex(
        ['2025-01-02 15:00:00'],
        tz=UTC,
    ).tz_convert(_ET)
    df = pd.DataFrame(
        {
            'Open': [150.0],
            'High': [150.0],
            'Low': [150.0],
            'Close': [150.0],
            'Volume': [0],
        },
        index=idx,
    )
    ticker = MagicMock()
    ticker.history.return_value = df
    assert _fetch_premarket_price(ticker) is None


@patch('fastapistock.repositories.us_stock_repo.time.sleep')
@patch(_PATCH_DATETIME)
def test_fetch_premarket_price_returns_none_on_exception(
    mock_dt: MagicMock,
    _mock_sleep: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'fastapistock.repositories.us_stock_repo.PREMARKET_MAX_RETRIES', 0
    )
    mock_dt.now.return_value = _PREMARKET_NOW
    ticker = MagicMock()
    ticker.history.side_effect = RuntimeError('network error')
    assert _fetch_premarket_price(ticker) is None


@patch(_PATCH_DATETIME)
def test_fetch_premarket_price_rounds_to_two_decimals(mock_dt: MagicMock) -> None:
    mock_dt.now.return_value = _PREMARKET_NOW
    ticker = MagicMock()
    ticker.history.return_value = _make_premarket_hist(185.123456)
    result = _fetch_premarket_price(ticker)
    assert result == 185.12


@patch(_PATCH_DATETIME)
def test_fetch_premarket_price_returns_none_outside_window(mock_dt: MagicMock) -> None:
    """After 09:30 ET the gate must short-circuit before any yfinance call."""
    mock_dt.now.return_value = _POSTMARKET_NOW
    ticker = MagicMock()
    ticker.history.return_value = _make_premarket_hist(185.5)  # data exists
    result = _fetch_premarket_price(ticker)
    assert result is None
    ticker.history.assert_not_called()


# ---------------------------------------------------------------------------
# fetch_us_stock integration tests
# ---------------------------------------------------------------------------


@patch('fastapistock.repositories.us_stock_repo.yf.Ticker')
@patch('fastapistock.repositories.us_stock_repo.time.sleep')
def test_returns_rich_stock_data(
    mock_sleep: MagicMock, mock_ticker_cls: MagicMock
) -> None:
    mock_ticker = _make_ticker_mock(
        daily_hist=_make_hist(60),
        premarket_hist=_make_premarket_hist(185.5),
        info={'longName': 'Apple Inc.'},
    )
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_us_stock('AAPL')

    assert isinstance(result, RichStockData)
    assert result.symbol == 'AAPL'
    assert result.market == 'US'
    assert result.display_name == 'Apple Inc.'


@patch('fastapistock.repositories.us_stock_repo.yf.Ticker')
@patch('fastapistock.repositories.us_stock_repo.time.sleep')
def test_empty_history_raises_stock_not_found(
    mock_sleep: MagicMock, mock_ticker_cls: MagicMock
) -> None:
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()
    mock_ticker.info = {}
    mock_ticker_cls.return_value = mock_ticker

    with pytest.raises(StockNotFoundError):
        fetch_us_stock('INVALID')


@patch('fastapistock.repositories.us_stock_repo.yf.Ticker')
@patch('fastapistock.repositories.us_stock_repo.time.sleep')
def test_symbol_used_without_tw_suffix(
    mock_sleep: MagicMock, mock_ticker_cls: MagicMock
) -> None:
    mock_ticker = _make_ticker_mock(daily_hist=_make_hist(60))
    mock_ticker_cls.return_value = mock_ticker

    fetch_us_stock('AAPL')

    mock_ticker_cls.assert_called_once_with('AAPL')


@patch('fastapistock.repositories.us_stock_repo.yf.Ticker')
@patch('fastapistock.repositories.us_stock_repo.time.sleep')
def test_price_and_change_calculated(
    mock_sleep: MagicMock, mock_ticker_cls: MagicMock
) -> None:
    hist = _make_hist(60, price=150.0)
    mock_ticker = _make_ticker_mock(daily_hist=hist)
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_us_stock('TSLA')

    assert result.price == pytest.approx(150.0, rel=0.01)
    assert result.prev_close == pytest.approx(150.0, rel=0.01)
    assert result.change == pytest.approx(0.0, abs=0.01)


@patch(_PATCH_DATETIME)
@patch('fastapistock.repositories.us_stock_repo.yf.Ticker')
@patch('fastapistock.repositories.us_stock_repo.time.sleep')
def test_premarket_price_populated_during_premarket(
    mock_sleep: MagicMock, mock_ticker_cls: MagicMock, mock_dt: MagicMock
) -> None:
    mock_dt.now.return_value = _PREMARKET_NOW
    mock_ticker = _make_ticker_mock(
        daily_hist=_make_hist(60),
        premarket_hist=_make_premarket_hist(188.0),
    )
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_us_stock('AAPL')

    assert result.premarket_price == pytest.approx(188.0, rel=0.001)


@patch('fastapistock.repositories.us_stock_repo.yf.Ticker')
@patch('fastapistock.repositories.us_stock_repo.time.sleep')
def test_premarket_price_none_outside_premarket(
    mock_sleep: MagicMock, mock_ticker_cls: MagicMock
) -> None:
    mock_ticker = _make_ticker_mock(
        daily_hist=_make_hist(60),
        premarket_hist=None,
    )
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_us_stock('AAPL')

    assert result.premarket_price is None


# ---------------------------------------------------------------------------
# Task 015-4: Retry logic unit tests
# ---------------------------------------------------------------------------

_PATCH_SLEEP = 'fastapistock.repositories.us_stock_repo.time.sleep'
_MAX_RETRIES_ATTR = 'fastapistock.repositories.us_stock_repo.PREMARKET_MAX_RETRIES'
_BASE_SLEEP_ATTR = 'fastapistock.repositories.us_stock_repo.PREMARKET_RETRY_BASE_SLEEP'


@patch(_PATCH_SLEEP)
@patch(_PATCH_DATETIME)
def test_premarket_retry_succeeds_on_second_attempt(
    mock_dt: MagicMock,
    mock_sleep: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First call returns empty DataFrame; second call returns valid data."""
    monkeypatch.setattr(_MAX_RETRIES_ATTR, 3)
    monkeypatch.setattr(_BASE_SLEEP_ATTR, 1.0)
    mock_dt.now.return_value = _PREMARKET_NOW

    ticker = MagicMock()
    ticker.history.side_effect = [pd.DataFrame(), _make_premarket_hist(190.0)]

    result = _fetch_premarket_price(ticker)

    assert result == pytest.approx(190.0, rel=0.001)
    mock_sleep.assert_called_once_with(1.0)


@patch(_PATCH_SLEEP)
@patch(_PATCH_DATETIME)
def test_premarket_retry_exhausted_returns_none(
    mock_dt: MagicMock,
    mock_sleep: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All (MAX_RETRIES + 1) attempts raise Exception; must return None."""
    monkeypatch.setattr(_MAX_RETRIES_ATTR, 3)
    monkeypatch.setattr(_BASE_SLEEP_ATTR, 1.0)
    mock_dt.now.return_value = _PREMARKET_NOW

    ticker = MagicMock()
    ticker.history.side_effect = RuntimeError('timeout')

    result = _fetch_premarket_price(ticker)

    assert result is None
    assert mock_sleep.call_count == 3
    sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
    assert sleep_calls == pytest.approx([1.0, 2.0, 4.0])


@patch(_PATCH_SLEEP)
@patch(_PATCH_DATETIME)
def test_premarket_retry_empty_df_all_attempts_returns_none(
    mock_dt: MagicMock,
    mock_sleep: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty DataFrame on every attempt is treated as retryable; returns None."""
    monkeypatch.setattr(_MAX_RETRIES_ATTR, 3)
    monkeypatch.setattr(_BASE_SLEEP_ATTR, 1.0)
    mock_dt.now.return_value = _PREMARKET_NOW

    ticker = MagicMock()
    ticker.history.return_value = pd.DataFrame()

    result = _fetch_premarket_price(ticker)

    assert result is None
    assert mock_sleep.call_count == 3


@patch(_PATCH_SLEEP)
@patch(_PATCH_DATETIME)
def test_premarket_no_retry_outside_window(
    mock_dt: MagicMock,
    mock_sleep: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ET time >= 09:30 must short-circuit before any history call or sleep."""
    monkeypatch.setattr(_MAX_RETRIES_ATTR, 3)
    monkeypatch.setattr(_BASE_SLEEP_ATTR, 1.0)
    mock_dt.now.return_value = _POSTMARKET_NOW

    ticker = MagicMock()

    result = _fetch_premarket_price(ticker)

    assert result is None
    ticker.history.assert_not_called()
    mock_sleep.assert_not_called()


@patch(_PATCH_SLEEP)
@patch(_PATCH_DATETIME)
def test_premarket_max_retries_zero_no_sleep(
    mock_dt: MagicMock,
    mock_sleep: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PREMARKET_MAX_RETRIES=0 means one attempt only; sleep must not be called."""
    monkeypatch.setattr(_MAX_RETRIES_ATTR, 0)
    monkeypatch.setattr(_BASE_SLEEP_ATTR, 1.0)
    mock_dt.now.return_value = _PREMARKET_NOW

    ticker = MagicMock()
    ticker.history.side_effect = RuntimeError('network error')

    result = _fetch_premarket_price(ticker)

    assert result is None
    ticker.history.assert_called_once()
    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# QA-added edge case tests: ET window boundaries and custom base sleep
# ---------------------------------------------------------------------------

_BOUNDARY_04_00 = datetime(2025, 1, 2, 4, 0, 0, tzinfo=_ET)  # exactly 04:00 — inclusive
_BOUNDARY_09_29 = datetime(
    2025, 1, 2, 9, 29, 0, tzinfo=_ET
)  # 09:29 — last valid minute
_BOUNDARY_03_59 = datetime(2025, 1, 2, 3, 59, 0, tzinfo=_ET)  # 03:59 — before window
_BOUNDARY_09_30 = datetime(
    2025, 1, 2, 9, 30, 0, tzinfo=_ET
)  # exactly 09:30 — exclusive


@patch(_PATCH_SLEEP)
@patch(_PATCH_DATETIME)
def test_premarket_window_boundary_exactly_0400_is_inside(
    mock_dt: MagicMock,
    mock_sleep: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ET 04:00:00 is the inclusive lower bound — fetch must be attempted."""
    monkeypatch.setattr(_MAX_RETRIES_ATTR, 0)
    monkeypatch.setattr(_BASE_SLEEP_ATTR, 1.0)
    mock_dt.now.return_value = _BOUNDARY_04_00

    ticker = MagicMock()
    ticker.history.return_value = _make_premarket_hist(180.0)

    result = _fetch_premarket_price(ticker)

    assert result == pytest.approx(180.0, rel=0.001)
    ticker.history.assert_called_once()


@patch(_PATCH_SLEEP)
@patch(_PATCH_DATETIME)
def test_premarket_window_boundary_0929_is_inside(
    mock_dt: MagicMock,
    mock_sleep: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ET 09:29 is the last valid minute — fetch must be attempted."""
    monkeypatch.setattr(_MAX_RETRIES_ATTR, 0)
    monkeypatch.setattr(_BASE_SLEEP_ATTR, 1.0)
    mock_dt.now.return_value = _BOUNDARY_09_29

    ticker = MagicMock()
    ticker.history.return_value = _make_premarket_hist(182.0)

    result = _fetch_premarket_price(ticker)

    assert result == pytest.approx(182.0, rel=0.001)
    ticker.history.assert_called_once()


@patch(_PATCH_SLEEP)
@patch(_PATCH_DATETIME)
def test_premarket_window_boundary_0359_is_outside(
    mock_dt: MagicMock,
    mock_sleep: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ET 03:59 is before pre-market window; short-circuits without any call."""
    monkeypatch.setattr(_MAX_RETRIES_ATTR, 3)
    monkeypatch.setattr(_BASE_SLEEP_ATTR, 1.0)
    mock_dt.now.return_value = _BOUNDARY_03_59

    ticker = MagicMock()

    result = _fetch_premarket_price(ticker)

    assert result is None
    ticker.history.assert_not_called()
    mock_sleep.assert_not_called()


@patch(_PATCH_SLEEP)
@patch(_PATCH_DATETIME)
def test_premarket_window_boundary_exactly_0930_is_outside(
    mock_dt: MagicMock,
    mock_sleep: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ET 09:30:00 is the exclusive upper bound; short-circuits without any call."""
    monkeypatch.setattr(_MAX_RETRIES_ATTR, 3)
    monkeypatch.setattr(_BASE_SLEEP_ATTR, 1.0)
    mock_dt.now.return_value = _BOUNDARY_09_30

    ticker = MagicMock()

    result = _fetch_premarket_price(ticker)

    assert result is None
    ticker.history.assert_not_called()
    mock_sleep.assert_not_called()


@patch(_PATCH_SLEEP)
@patch(_PATCH_DATETIME)
def test_premarket_retry_uses_custom_base_sleep(
    mock_dt: MagicMock,
    mock_sleep: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With PREMARKET_RETRY_BASE_SLEEP=0.5 the sleep sequence must be 0.5, 1.0, 2.0."""
    monkeypatch.setattr(_MAX_RETRIES_ATTR, 3)
    monkeypatch.setattr(_BASE_SLEEP_ATTR, 0.5)
    mock_dt.now.return_value = _PREMARKET_NOW

    ticker = MagicMock()
    ticker.history.side_effect = RuntimeError('timeout')

    result = _fetch_premarket_price(ticker)

    assert result is None
    assert mock_sleep.call_count == 3
    sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
    assert sleep_calls == pytest.approx([0.5, 1.0, 2.0])
