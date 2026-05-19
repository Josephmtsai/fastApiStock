# Daily PnL Delta Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add scheduled total PnL comparison versus separate TW and US previous-close baselines.

**Architecture:** Reuse existing Google Sheets PnL readers and Redis snapshot patterns. Add daily market-close snapshots, calculate total deltas in `portfolio_service`, and wire the scheduler so quote pushes include or follow with a compact delta message.

**Tech Stack:** Python 3.11, FastAPI, APScheduler, Redis cache wrapper, pytest, Ruff, mypy.

---

## File Map

- Modify `src/fastapistock/repositories/portfolio_snapshot_repo.py`
  - Add daily snapshot dataclass or extend current snapshot helpers.
  - Add `save_daily()` / `get_daily()` helpers keyed by market and trading date.
- Modify `src/fastapistock/services/portfolio_service.py`
  - Add pure calculation helpers for previous-close PnL deltas.
  - Add formatter for the Telegram PnL delta block.
- Modify `src/fastapistock/scheduler.py`
  - Add TW and US close-baseline jobs.
  - Add safe scheduled helper to send current PnL delta after quote pushes if
    appending to existing quote messages is not clean.
- Modify or extend `src/fastapistock/services/telegram_service.py` only if the
  existing send API supports a small, low-risk append point.
- Modify `tests/test_portfolio_snapshot_repo.py`.
- Modify `tests/test_portfolio_service.py`.
- Modify `tests/test_scheduler.py`.

## Task 1 - Daily Snapshot Repository

**Files:**

- Modify: `src/fastapistock/repositories/portfolio_snapshot_repo.py`
- Test: `tests/test_portfolio_snapshot_repo.py`

- [ ] Step 1: Write failing tests for daily snapshot round-trip.

Add tests that save and read separate TW and US daily snapshots:

```python
def test_daily_save_get_roundtrip_tw() -> None:
    snapshot = PortfolioSnapshot(
        pnl_tw=123456.0,
        pnl_us=0.0,
        timestamp=datetime(2026, 5, 19, 14, 10, tzinfo=_TZ),
    )
    save_daily('TW', '2026-05-19', snapshot)

    got = get_daily('TW', '2026-05-19')

    assert got is not None
    assert got.pnl_tw == 123456.0
    assert got.timestamp == datetime(2026, 5, 19, 14, 10, tzinfo=_TZ)


def test_daily_save_get_roundtrip_us_uses_us_trading_date() -> None:
    snapshot = PortfolioSnapshot(
        pnl_tw=0.0,
        pnl_us=-2500.0,
        timestamp=datetime(2026, 5, 20, 4, 10, tzinfo=_TZ),
    )
    save_daily('US', '2026-05-19', snapshot)

    got = get_daily('US', '2026-05-19')

    assert got is not None
    assert got.pnl_us == -2500.0
```

- [ ] Step 2: Run focused test and confirm failure.

Run:

```powershell
uv run pytest tests/test_portfolio_snapshot_repo.py -v
```

Expected: FAIL because `save_daily` and `get_daily` do not exist.

- [ ] Step 3: Implement daily snapshot helpers.

Add a daily prefix:

```python
_DAILY_PREFIX: str = 'portfolio:snapshot:daily'
```

Add helpers:

```python
def _normalize_market(market: str) -> str:
    normalized = market.strip().upper()
    if normalized not in {'TW', 'US'}:
        raise ValueError(f'Unsupported market: {market}')
    return normalized


def save_daily(market: str, trading_date: str, snapshot: PortfolioSnapshot) -> None:
    """Persist a daily market-close snapshot.

    Args:
        market: Market code, either ``TW`` or ``US``.
        trading_date: Market trading date in ``YYYY-MM-DD`` format.
        snapshot: Snapshot to persist.
    """
    normalized = _normalize_market(market).lower()
    _save(f'{_DAILY_PREFIX}:{normalized}:{trading_date}', snapshot)


def get_daily(market: str, trading_date: str) -> PortfolioSnapshot | None:
    """Read a daily market-close snapshot.

    Args:
        market: Market code, either ``TW`` or ``US``.
        trading_date: Market trading date in ``YYYY-MM-DD`` format.

    Returns:
        PortfolioSnapshot when present and valid, otherwise None.
    """
    normalized = _normalize_market(market).lower()
    return _load(f'{_DAILY_PREFIX}:{normalized}:{trading_date}')
```

- [ ] Step 4: Run focused tests and confirm pass.

Run:

```powershell
uv run pytest tests/test_portfolio_snapshot_repo.py -v
```

Expected: PASS.

## Task 2 - PnL Delta Calculation And Formatting

**Files:**

- Modify: `src/fastapistock/services/portfolio_service.py`
- Test: `tests/test_portfolio_service.py`

- [ ] Step 1: Write failing tests for total delta formatting.

Add tests for both complete and missing-baseline cases:

```python
def test_format_daily_pnl_delta_complete() -> None:
    text = format_daily_pnl_delta(
        current_tw=108000.0,
        current_us=12000.0,
        previous_tw=100000.0,
        previous_us=15000.0,
    )

    assert '+8,000 TWD' in text
    assert '-3,000 TWD' in text
    assert '+5,000 TWD' in text
    assert '+120,000 TWD' in text
    assert '+115,000 TWD' in text


def test_format_daily_pnl_delta_missing_baseline() -> None:
    text = format_daily_pnl_delta(
        current_tw=108000.0,
        current_us=12000.0,
        previous_tw=None,
        previous_us=None,
    )

    assert 'No previous-close baseline yet' in text
    assert '+120,000 TWD' in text
```

- [ ] Step 2: Run focused tests and confirm failure.

Run:

```powershell
uv run pytest tests/test_portfolio_service.py -v
```

Expected: FAIL because `format_daily_pnl_delta` does not exist.

- [ ] Step 3: Implement pure formatter.

Add public function:

```python
def _fmt_twd(value: float) -> str:
    sign = '+' if value >= 0 else '-'
    return f'{sign}{abs(value):,.0f} TWD'


def format_daily_pnl_delta(
    *,
    current_tw: float | None,
    current_us: float | None,
    previous_tw: float | None,
    previous_us: float | None,
) -> str:
    """Format daily PnL delta versus previous market close baselines."""
    lines = ['Portfolio PnL vs previous close', '']
    current_values = [value for value in (current_tw, current_us) if value is not None]
    current_total = sum(current_values)

    if previous_tw is None and previous_us is None:
        lines.append('No previous-close baseline yet.')
        lines.append(f'Current total: {_fmt_twd(current_total)}')
        return '\n'.join(lines)

    if current_tw is not None and previous_tw is not None:
        lines.append(f'TW: {_fmt_twd(current_tw - previous_tw)}')
    else:
        lines.append('TW: current PnL or baseline unavailable')

    if current_us is not None and previous_us is not None:
        lines.append(f'US: {_fmt_twd(current_us - previous_us)}')
    else:
        lines.append('US: current PnL or baseline unavailable')

    lines.append('')
    if None not in (current_tw, current_us, previous_tw, previous_us):
        previous_total = previous_tw + previous_us
        total_delta = current_total - previous_total
        lines.append(f'Total: {_fmt_twd(total_delta)}')
        lines.append(f'Current total: {_fmt_twd(current_total)}')
        lines.append(f'Previous close baseline: {_fmt_twd(previous_total)}')
    else:
        lines.append(
            'Total delta unavailable until both markets have current PnL and baselines.'
        )
    return '\n'.join(lines)
```

- [ ] Step 4: Run focused tests and confirm pass.

Run:

```powershell
uv run pytest tests/test_portfolio_service.py -v
```

Expected: PASS.

## Task 3 - Baseline Capture Service Helpers

**Files:**

- Modify: `src/fastapistock/services/portfolio_service.py`
- Test: `tests/test_portfolio_service.py`

- [ ] Step 1: Write tests for capture and read behavior with mocks.

Test TW uses current date and US can accept caller-provided trading date:

```python
def test_save_daily_close_snapshot_tw(monkeypatch: pytest.MonkeyPatch) -> None:
    saved: dict[str, object] = {}
    monkeypatch.setattr(portfolio_service, 'fetch_pnl_tw', lambda: 5000.0)
    monkeypatch.setattr(
        portfolio_service.portfolio_snapshot_repo,
        'save_daily',
        lambda market, trading_date, snapshot: saved.update(
            {'market': market, 'trading_date': trading_date, 'snapshot': snapshot}
        ),
    )

    ok = portfolio_service.save_daily_close_snapshot(
        market='TW',
        trading_date='2026-05-19',
        captured_at=datetime(2026, 5, 19, 14, 10, tzinfo=_TZ),
    )

    assert ok is True
    assert saved['market'] == 'TW'
    assert saved['trading_date'] == '2026-05-19'
```

- [ ] Step 2: Run tests and confirm failure.

Run:

```powershell
uv run pytest tests/test_portfolio_service.py -v
```

Expected: FAIL because `save_daily_close_snapshot` does not exist.

- [ ] Step 3: Implement helper.

Update imports:

```python
from datetime import datetime

from fastapistock.repositories import portfolio_snapshot_repo
from fastapistock.repositories.portfolio_repo import (
    fetch_pnl_tw,
    fetch_pnl_us,
)
from fastapistock.repositories.portfolio_snapshot_repo import PortfolioSnapshot
```

Implement `save_daily_close_snapshot()` using `fetch_pnl_tw()` for TW and
`fetch_pnl_us()` for US. Return `False` when current PnL is unavailable.

```python
def save_daily_close_snapshot(
    *,
    market: str,
    trading_date: str,
    captured_at: datetime,
) -> bool:
    """Capture one market's close PnL baseline."""
    normalized = market.strip().upper()
    if normalized == 'TW':
        pnl_tw = fetch_pnl_tw()
        if pnl_tw is None:
            return False
        snapshot = PortfolioSnapshot(pnl_tw=pnl_tw, pnl_us=0.0, timestamp=captured_at)
    elif normalized == 'US':
        pnl_us = fetch_pnl_us()
        if pnl_us is None:
            return False
        snapshot = PortfolioSnapshot(pnl_tw=0.0, pnl_us=pnl_us, timestamp=captured_at)
    else:
        raise ValueError(f'Unsupported market: {market}')
    portfolio_snapshot_repo.save_daily(normalized, trading_date, snapshot)
    return True
```

- [ ] Step 4: Add read-side reply helper tests.

Add a test that mocks current PnL and daily snapshots:

```python
def test_get_daily_pnl_delta_reply_uses_daily_baselines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(portfolio_service, 'fetch_pnl_tw', lambda: 108000.0)
    monkeypatch.setattr(portfolio_service, 'fetch_pnl_us', lambda: 12000.0)

    def fake_get_daily(market: str, trading_date: str) -> PortfolioSnapshot | None:
        if market == 'TW' and trading_date == '2026-05-19':
            return PortfolioSnapshot(
                pnl_tw=100000.0,
                pnl_us=0.0,
                timestamp=datetime(2026, 5, 19, 14, 10, tzinfo=_TZ),
            )
        if market == 'US' and trading_date == '2026-05-19':
            return PortfolioSnapshot(
                pnl_tw=0.0,
                pnl_us=15000.0,
                timestamp=datetime(2026, 5, 20, 4, 10, tzinfo=_TZ),
            )
        return None

    monkeypatch.setattr(
        portfolio_service.portfolio_snapshot_repo,
        'get_daily',
        fake_get_daily,
    )

    text = portfolio_service.get_daily_pnl_delta_reply(
        tw_trading_date='2026-05-19',
        us_trading_date='2026-05-19',
    )

    assert '+5,000 TWD' in text
```

- [ ] Step 5: Implement `get_daily_pnl_delta_reply()`.

```python
def get_daily_pnl_delta_reply(
    *,
    tw_trading_date: str,
    us_trading_date: str,
) -> str:
    """Build daily PnL delta text using current PnL and close baselines."""
    current_tw = fetch_pnl_tw()
    current_us = fetch_pnl_us()
    tw_snapshot = portfolio_snapshot_repo.get_daily('TW', tw_trading_date)
    us_snapshot = portfolio_snapshot_repo.get_daily('US', us_trading_date)
    return format_daily_pnl_delta(
        current_tw=current_tw,
        current_us=current_us,
        previous_tw=tw_snapshot.pnl_tw if tw_snapshot is not None else None,
        previous_us=us_snapshot.pnl_us if us_snapshot is not None else None,
    )
```

- [ ] Step 6: Run tests and confirm pass.

Run:

```powershell
uv run pytest tests/test_portfolio_service.py -v
```

Expected: PASS.

## Task 4 - Scheduler Close Snapshot Jobs

**Files:**

- Modify: `src/fastapistock/scheduler.py`
- Test: `tests/test_scheduler.py`

- [ ] Step 1: Write tests for trading-date mapping.

Add tests for TW and US close snapshot helpers:

```python
def test_us_close_snapshot_uses_previous_us_trading_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        scheduler.portfolio_service,
        'save_daily_close_snapshot',
        lambda *, market, trading_date, captured_at: calls.append(
            (market, trading_date)
        )
        or True,
    )

    scheduler.capture_us_close_snapshot(
        datetime(2026, 5, 20, 4, 10, tzinfo=ZoneInfo('Asia/Taipei'))
    )

    assert calls == [('US', '2026-05-19')]
```

- [ ] Step 2: Run scheduler tests and confirm failure.

Run:

```powershell
uv run pytest tests/test_scheduler.py -v
```

Expected: FAIL because close snapshot helpers do not exist.

- [ ] Step 3: Implement scheduler helpers and jobs.

Add imports:

```python
from datetime import datetime, timedelta
from fastapistock.services import portfolio_service
```

Add helpers:

```python
def capture_tw_close_snapshot(now: datetime | None = None) -> None:
    """Capture TW close PnL baseline for the current Taiwan trading date."""
    local = (now or datetime.now(_TZ)).astimezone(_TZ)
    try:
        portfolio_service.save_daily_close_snapshot(
            market='TW',
            trading_date=local.date().isoformat(),
            captured_at=local,
        )
    except Exception:
        logger.exception('TW daily close snapshot failed')


def capture_us_close_snapshot(now: datetime | None = None) -> None:
    """Capture US close PnL baseline for the previous US trading date."""
    local = (now or datetime.now(_TZ)).astimezone(_TZ)
    trading_date = (local.date() - timedelta(days=1)).isoformat()
    try:
        portfolio_service.save_daily_close_snapshot(
            market='US',
            trading_date=trading_date,
            captured_at=local,
        )
    except Exception:
        logger.exception('US daily close snapshot failed')
```

Add cron jobs in `build_scheduler()`:

```python
scheduler.add_job(
    capture_tw_close_snapshot,
    trigger=CronTrigger(day_of_week='mon-fri', hour=14, minute=10, timezone=str(_TZ)),
    id='tw_daily_close_snapshot',
    name='TW daily close PnL snapshot',
    replace_existing=True,
)
scheduler.add_job(
    capture_us_close_snapshot,
    trigger=CronTrigger(day_of_week='tue-sat', hour=4, minute=10, timezone=str(_TZ)),
    id='us_daily_close_snapshot',
    name='US daily close PnL snapshot',
    replace_existing=True,
)
```

- [ ] Step 4: Run scheduler tests and confirm pass.

Run:

```powershell
uv run pytest tests/test_scheduler.py -v
```

Expected: PASS.

## Task 5 - Scheduled Push Delta Message

**Files:**

- Modify: `src/fastapistock/scheduler.py`
- Modify only if needed: `src/fastapistock/services/telegram_service.py`
- Test: `tests/test_scheduler.py`

- [ ] Step 1: Write tests that `_scheduled_push` still sends quotes when PnL fails.

Add a test shaped like this:

```python
def test_scheduled_push_keeps_quote_push_when_pnl_delta_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    active_time = datetime(2026, 5, 19, 9, 0, tzinfo=ZoneInfo('Asia/Taipei'))

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: ZoneInfo | None = None) -> datetime:
            return active_time

    monkeypatch.setattr(scheduler, 'datetime', FixedDateTime)
    monkeypatch.setattr(scheduler, 'push_tw_stocks', lambda: calls.append('tw'))
    monkeypatch.setattr(
        scheduler,
        '_send_daily_pnl_delta',
        lambda: (_ for _ in ()).throw(RuntimeError('pnl failed')),
    )

    scheduler._scheduled_push()

    assert calls == ['tw']
```

Expected behavior: the test should fail before implementation if
`_scheduled_push()` does not isolate PnL failures.

- [ ] Step 2: Implement a safe `_send_daily_pnl_delta()` helper.

Add helper functions in `scheduler.py`:

```python
def _previous_tw_trading_date(now: datetime) -> str:
    local = now.astimezone(_TZ).date()
    return (local - timedelta(days=1)).isoformat()


def _previous_us_trading_date(now: datetime) -> str:
    local = now.astimezone(_TZ).date()
    if now.astimezone(_TZ).hour <= 4:
        return (local - timedelta(days=1)).isoformat()
    return local.isoformat()


def _send_daily_pnl_delta(now: datetime | None = None) -> None:
    """Send compact PnL delta message after scheduled quote push."""
    if not TELEGRAM_USER_ID:
        logger.warning('TELEGRAM_USER_ID not set; skipping PnL delta push')
        return
    local = (now or datetime.now(_TZ)).astimezone(_TZ)
    try:
        text = portfolio_service.get_daily_pnl_delta_reply(
            tw_trading_date=_previous_tw_trading_date(local),
            us_trading_date=_previous_us_trading_date(local),
        )
        if text:
            portfolio_service.send_daily_pnl_delta_message(TELEGRAM_USER_ID, text)
    except Exception:
        logger.exception('Daily PnL delta push failed')
```

If `send_daily_pnl_delta_message()` fits better in `telegram_service.py`, keep
`portfolio_service.get_daily_pnl_delta_reply()` pure and call
`telegram_service.send_text_message()` or a new narrow helper from scheduler.
Use `httpx.post(..., timeout=10)` and no hardcoded secrets.

Concrete minimal implementation option in `telegram_service.py`:

```python
def send_text_message(user_id: str, text: str) -> bool:
    """Send a plain text Telegram message."""
    if not TELEGRAM_TOKEN:
        logger.error('TELEGRAM_TOKEN is not configured')
        return False
    url = f'{_TELEGRAM_API_BASE}/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {'chat_id': user_id, 'text': text}
    try:
        response = httpx.post(url, json=payload, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        return True
    except httpx.HTTPStatusError as exc:
        logger.error(
            'Telegram API error for text message user_id=%s: %s %s',
            user_id,
            exc.response.status_code,
            exc.response.text,
        )
        return False
    except httpx.RequestError as exc:
        logger.error('Telegram text request failed for user_id=%s: %s', user_id, exc)
        return False
```

Then scheduler can use:

```python
from fastapistock.services.telegram_service import send_text_message

...
send_text_message(TELEGRAM_USER_ID, text)
```

- [ ] Step 3: Call `_send_daily_pnl_delta()` after market quote push.

Wrap the call so quote pushes are never blocked:

```python
def _safe_send_daily_pnl_delta() -> None:
    try:
        _send_daily_pnl_delta()
    except Exception:
        logger.exception('Scheduled PnL delta wrapper failed')
```

Update `_scheduled_push()`:

```python
if is_tw_market_window(now):
    logger.info('TW market window active - pushing')
    push_tw_stocks()
    _safe_send_daily_pnl_delta()

if is_us_market_window(now):
    logger.info('US market window active - pushing')
    push_us_stocks()
    _safe_send_daily_pnl_delta()
```

- [ ] Step 4: Run scheduler tests.

Run:

```powershell
uv run pytest tests/test_scheduler.py -v
```

Expected: PASS.

## Task 6 - Validation

- [ ] Run focused tests:

```powershell
uv run pytest tests/test_portfolio_snapshot_repo.py tests/test_portfolio_service.py tests/test_scheduler.py -v
```

Expected: PASS.

- [ ] Run formatting and lint:

```powershell
uv run ruff check . --fix
uv run ruff format .
```

Expected: no remaining Ruff errors.

- [ ] Run type checking:

```powershell
uv run mypy src/
```

Expected: PASS.

- [ ] Run full pre-commit:

```powershell
uv run pre-commit run --all-files
```

Expected: PASS.

## Acceptance Criteria Mapping

- US1: Tasks 2 and 5.
- US2: Tasks 1, 3, and 4.
- US3: Tasks 2, 3, 4, and 5.

## Definition of Done

- Daily TW/US close snapshots are stored separately in Redis.
- US close snapshot uses previous US trading date when captured in Taiwan early
  morning.
- Scheduled quote pushes continue when PnL comparison fails.
- PnL comparison reports total increase/decrease versus previous close.
- Focused tests, Ruff, mypy, and pre-commit pass.
