# API Contracts: fastApiStock

**Date**: 2026-04-03
**Base URL**: `http://localhost:8000`
**Response envelope**: all responses use `ResponseEnvelope[T]`

---

## GET /health

**Purpose**: Liveness check
**Auth**: None
**Rate limit**: None

**Response 200**:
```json
{
  "status": "success",
  "data": { "status": "ok" },
  "message": ""
}
```

---

## GET /stocks/{symbol}

**Purpose**: Fetch latest quote for a TW stock symbol (e.g., `2330`)
**Auth**: None
**Rate limit**: 60 req/min per IP

**Path params**:
| Param | Type | Constraint |
|-------|------|-----------|
| `symbol` | `str` | 4-digit TW stock code |

**Response 200**:
```json
{
  "status": "success",
  "data": {
    "symbol": "2330",
    "name": "台積電",
    "price": 980.0,
    "change": 5.0,
    "volume": 12345678,
    "timestamp": "2026-04-03T09:30:00+08:00"
  },
  "message": ""
}
```

**Response 404** (symbol not found):
```json
{
  "status": "error",
  "data": null,
  "message": "Symbol 9999 not found"
}
```

---

## GET /stocks/{symbol}/history

**Purpose**: Fetch OHLCV history for a TW stock
**Auth**: None
**Rate limit**: 30 req/min per IP

**Path params**: `symbol` (same as above)

**Query params**:
| Param | Type | Default | Constraint |
|-------|------|---------|-----------|
| `start` | `date` | 30 days ago | ISO 8601 |
| `end` | `date` | today | ISO 8601 |
| `limit` | `int` | 30 | 1–365 |

**Response 200**:
```json
{
  "status": "success",
  "data": [
    { "date": "2026-04-03", "open": 975.0, "high": 985.0, "low": 970.0, "close": 980.0, "volume": 12345678 }
  ],
  "message": ""
}
```

**Response 422** (invalid query params):
```json
{
  "status": "error",
  "data": null,
  "message": "end must be >= start"
}
```
