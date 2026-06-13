"""Unit tests for fx_service.get_usd_twd_rate()."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import fastapistock.services.fx_service as fx_module
from fastapistock.services.fx_service import get_usd_twd_rate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hist(close: float) -> pd.DataFrame:
    """Return a minimal DataFrame mimicking yfinance history output."""
    return pd.DataFrame({'Close': [close]}, index=[date.today()])


# ---------------------------------------------------------------------------
# AC-1: Redis miss → yfinance called, result written to cache
# ---------------------------------------------------------------------------


def test_cache_miss_fetches_live_rate_and_writes_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr('fastapistock.services.fx_service.FX_CACHE_TTL', 14400)

    cache_store: dict[str, dict[str, object]] = {}

    def fake_get(key: str) -> dict[str, object] | None:
        return cache_store.get(key)

    def fake_put(key: str, value: dict[str, object], ttl: int) -> None:
        cache_store[key] = value

    monkeypatch.setattr(fx_module.redis_cache, 'get', fake_get)
    monkeypatch.setattr(fx_module.redis_cache, 'put', fake_put)
    monkeypatch.setattr('time.sleep', lambda _: None)

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_hist(32.5)

    with patch(
        'fastapistock.services.fx_service.yfinance.Ticker',
        return_value=mock_ticker,
    ):
        rate = get_usd_twd_rate()

    assert rate == pytest.approx(32.5)
    key = f'fx:usd_twd:{date.today().isoformat()}'
    assert cache_store[key] == {'rate': pytest.approx(32.5)}
    mock_ticker.history.assert_called_once()


# ---------------------------------------------------------------------------
# AC-2: Redis hit → yfinance NOT called
# ---------------------------------------------------------------------------


def test_cache_hit_does_not_call_yfinance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = f'fx:usd_twd:{date.today().isoformat()}'
    cached_value: dict[str, object] = {'rate': 31.75}

    monkeypatch.setattr(fx_module.redis_cache, 'get', lambda _k: cached_value)
    monkeypatch.setattr(fx_module.redis_cache, 'put', lambda *_a, **_k: None)

    with patch('fastapistock.services.fx_service.yfinance.Ticker') as mock_ticker_cls:
        rate = get_usd_twd_rate()

    assert rate == pytest.approx(31.75)
    mock_ticker_cls.assert_not_called()
    _ = key  # suppress unused-variable warning


# ---------------------------------------------------------------------------
# AC-3: yfinance raises Exception → returns None
# ---------------------------------------------------------------------------


def test_yfinance_exception_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fx_module.redis_cache, 'get', lambda _k: None)
    monkeypatch.setattr(fx_module.redis_cache, 'put', lambda *_a, **_k: None)
    monkeypatch.setattr('time.sleep', lambda _: None)

    with patch(
        'fastapistock.services.fx_service.yfinance.Ticker',
        side_effect=RuntimeError('network error'),
    ):
        rate = get_usd_twd_rate()

    assert rate is None


# ---------------------------------------------------------------------------
# AC-4: yfinance returns empty DataFrame → returns None
# ---------------------------------------------------------------------------


def test_yfinance_empty_dataframe_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fx_module.redis_cache, 'get', lambda _k: None)
    monkeypatch.setattr(fx_module.redis_cache, 'put', lambda *_a, **_k: None)
    monkeypatch.setattr('time.sleep', lambda _: None)

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()

    with patch(
        'fastapistock.services.fx_service.yfinance.Ticker',
        return_value=mock_ticker,
    ):
        rate = get_usd_twd_rate()

    assert rate is None


# ---------------------------------------------------------------------------
# AC-8: FX_CACHE_TTL env var can be overridden
# ---------------------------------------------------------------------------


def test_cache_ttl_is_passed_to_redis_put(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr('fastapistock.services.fx_service.FX_CACHE_TTL', 999)

    put_calls: list[tuple[str, dict[str, object], int]] = []

    def fake_put(key: str, value: dict[str, object], ttl: int) -> None:
        put_calls.append((key, value, ttl))

    monkeypatch.setattr(fx_module.redis_cache, 'get', lambda _k: None)
    monkeypatch.setattr(fx_module.redis_cache, 'put', fake_put)
    monkeypatch.setattr('time.sleep', lambda _: None)

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_hist(30.0)

    with patch(
        'fastapistock.services.fx_service.yfinance.Ticker',
        return_value=mock_ticker,
    ):
        get_usd_twd_rate()

    assert len(put_calls) == 1
    assert put_calls[0][2] == 999


# ---------------------------------------------------------------------------
# Extra edge cases (QA additions)
# ---------------------------------------------------------------------------


def test_malformed_cache_entry_missing_key_falls_through_to_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cache hit whose value lacks 'rate' key must fall through to live fetch."""
    # Cache returns a dict without 'rate' key
    monkeypatch.setattr(fx_module.redis_cache, 'get', lambda _k: {'wrong_key': 99.0})
    monkeypatch.setattr('time.sleep', lambda _: None)

    put_calls: list[object] = []
    monkeypatch.setattr(
        fx_module.redis_cache,
        'put',
        lambda *a, **kw: put_calls.append(a),
    )

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_hist(32.0)

    with patch(
        'fastapistock.services.fx_service.yfinance.Ticker',
        return_value=mock_ticker,
    ):
        rate = get_usd_twd_rate()

    # Should fall through to live fetch and return live rate
    assert rate == pytest.approx(32.0)
    # And write fresh value to cache
    assert len(put_calls) == 1


def test_malformed_cache_entry_non_numeric_rate_falls_through_to_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cache hit whose 'rate' value is a non-numeric string must fall through."""
    monkeypatch.setattr(
        fx_module.redis_cache, 'get', lambda _k: {'rate': 'not-a-number'}
    )
    monkeypatch.setattr('time.sleep', lambda _: None)

    put_calls: list[object] = []
    monkeypatch.setattr(
        fx_module.redis_cache,
        'put',
        lambda *a, **kw: put_calls.append(a),
    )

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_hist(31.0)

    with patch(
        'fastapistock.services.fx_service.yfinance.Ticker',
        return_value=mock_ticker,
    ):
        rate = get_usd_twd_rate()

    assert rate == pytest.approx(31.0)
    assert len(put_calls) == 1


def test_yfinance_none_rate_is_not_written_to_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When yfinance yields None (e.g. exception), nothing is written to cache."""
    monkeypatch.setattr(fx_module.redis_cache, 'get', lambda _k: None)
    monkeypatch.setattr('time.sleep', lambda _: None)

    put_calls: list[object] = []
    monkeypatch.setattr(
        fx_module.redis_cache,
        'put',
        lambda *a, **kw: put_calls.append(a),
    )

    with patch(
        'fastapistock.services.fx_service.yfinance.Ticker',
        side_effect=RuntimeError('timeout'),
    ):
        rate = get_usd_twd_rate()

    assert rate is None
    assert len(put_calls) == 0  # Nothing written to cache when fetch fails
