# Data Model: Portfolio PnL Command (`/pnl`)

**Date**: 2026-04-11 | **Branch**: `main`

---

## Source Cells

| Market | Sheet GID env var | Cell | Row (0-idx) | Col (0-idx) | Currency |
|--------|------------------|------|-------------|-------------|----------|
| TW | `GOOGLE_SHEETS_PORTFOLIO_GID_TW` | I19 | 18 | 8 | TWD |
| US | `GOOGLE_SHEETS_PORTFOLIO_GID_US` | H21 | 20 | 7 | TWD |

---

## New Constants — `portfolio_repo.py`

```python
_TW_PNL_ROW: int = 19   # Cell I20, 0-indexed
_TW_PNL_COL: int = 8    # Column I, 0-indexed
_US_PNL_ROW: int = 20   # Cell H21, 0-indexed
_US_PNL_COL: int = 7    # Column H, 0-indexed
```

---

## New Functions — `portfolio_repo.py`

### `fetch_pnl_tw() -> float | None`

Fetches the TW portfolio total unrealized PnL from cell I20 of the TW portfolio sheet.

- Returns `float` (may be negative) on success.
- Returns `None` when config is missing, HTTP fails, or cell is out of range.
- Uses `_SHEETS_CSV_URL` with `GOOGLE_SHEETS_ID` + `GOOGLE_SHEETS_PORTFOLIO_GID_TW`.
- Calls `_parse_number()` for comma-tolerant float parsing.
- Caches result in Redis under key `pnl:tw:{YYYY-MM-DD}` with TTL `PORTFOLIO_CACHE_TTL`.

### `fetch_pnl_us() -> float | None`

Fetches the US portfolio total unrealized PnL from cell H21 of the US portfolio sheet.

- Same contract as `fetch_pnl_tw()` but uses `GOOGLE_SHEETS_PORTFOLIO_GID_US`.
- Cache key: `pnl:us:{YYYY-MM-DD}`.

---

## New Service — `portfolio_service.py`

### `get_pnl_reply() -> str`

Orchestrates both repo calls and returns a formatted Telegram reply string.

```python
def get_pnl_reply() -> str:
    tw = fetch_pnl_tw()
    us = fetch_pnl_us()
    return _format_pnl_reply(tw, us)
```

### `_format_pnl_reply(tw_pnl: float | None, us_pnl: float | None) -> str`

Pure formatting function (testable in isolation).

**Output format (both available)**:
```
📈 投資組合未實現損益

🇹🇼 台股：+$1,234,567 TWD
🇺🇸 美股：+$890,123 TWD

合計：+$2,124,690 TWD
```

**Output format (one fails)**:
```
📈 投資組合未實現損益

🇹🇼 台股：無法取得
🇺🇸 美股：+$890,123 TWD

合計：無法計算（部分資料缺失）
```

**Output format (both fail)**:
```
📈 投資組合未實現損益

無法取得損益資料，請稍後再試
```

**Number format**: `f'{value:+,.0f}'` → `+1,234,567` or `-567,890`

---

## Webhook Changes — `webhook.py`

### Command dispatch addition

```python
elif cmd == '/pnl':
    reply = get_pnl_reply()
```

### Updated `_HELP_TEXT`

Add line: `/pnl — 投資組合未實現損益（台股＋美股）`

### `setMyCommands` startup (if applicable in `main.py`)

Add: `{"command": "pnl", "description": "投資組合未實現損益"}`

---

## Cache Key Convention

| Key | Value | TTL |
|-----|-------|-----|
| `pnl:tw:{YYYY-MM-DD}` | `str(float)` | `PORTFOLIO_CACHE_TTL` (default 3600 s) |
| `pnl:us:{YYYY-MM-DD}` | `str(float)` | `PORTFOLIO_CACHE_TTL` (default 3600 s) |

Date suffix ensures daily refresh; stale-day hits auto-expire.

---

## State / Error Flow

```
/pnl received
    │
    ▼
get_pnl_reply()
    ├── fetch_pnl_tw()
    │       ├── Redis hit → return cached float
    │       └── Redis miss → httpx GET CSV → parse row 19 col 8 → cache → return float
    │           └── on error → return None
    └── fetch_pnl_us()
            ├── Redis hit → return cached float
            └── Redis miss → httpx GET CSV → parse row 20 col 7 → cache → return float
                └── on error → return None
    │
    ▼
_format_pnl_reply(tw, us) → str
    │
    ▼
reply_to_chat(chat_id, reply)
```
