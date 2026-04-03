# Data Model: fastApiStock

**Date**: 2026-04-03

## Schemas (`src/schemas/`)

### `common.py` — Shared envelope

```python
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar('T')

class ResponseEnvelope(BaseModel, Generic[T]):
    status: Literal['success', 'error']
    data: T | None
    message: str
```

All route handlers return `ResponseEnvelope[<domain_model>]`.

### `stock.py` — Stock domain

| Model | Fields | Notes |
|-------|--------|-------|
| `StockQuote` | `symbol: str`, `name: str`, `price: float`, `change: float`, `volume: int`, `timestamp: datetime` | Real-time snapshot |
| `StockHistory` | `date: date`, `open: float`, `high: float`, `low: float`, `close: float`, `volume: int` | OHLCV record |
| `StockQueryParams` | `start: date \| None`, `end: date \| None`, `limit: int = 30` | Query string for `/history` |

## Config (`src/config.py`)

```python
class Settings(BaseModel):
    tw_stock_api_base_url: str   # from env TW_STOCK_API_BASE_URL
    cache_ttl_seconds: int = 300  # from env CACHE_TTL_SECONDS
    request_timeout: int = 10     # from env REQUEST_TIMEOUT
    rate_limit_per_minute: int = 60
```

## Cache Key Convention

```
cache/<symbol>/<YYYY-MM-DD>.json   # daily quote snapshot
cache/<symbol>/history/<YYYY-MM>.json  # monthly history chunk
```
