# Contract: `/pnl` Telegram Bot Command

**Date**: 2026-04-11 | **Branch**: `main`

---

## Command Spec

| Field | Value |
|-------|-------|
| Command | `/pnl` |
| Arguments | None |
| Auth | Authorized `TELEGRAM_USER_ID` only (same as all commands) |
| Reply mode | Plain text via `reply_to_chat(chat_id, text)` |

---

## Reply Format

### Normal — both markets available

```
📈 投資組合未實現損益

🇹🇼 台股：+$1,234,567 TWD
🇺🇸 美股：+$890,123 TWD

合計：+$2,124,690 TWD
```

### Partial failure — one market unavailable

```
📈 投資組合未實現損益

🇹🇼 台股：無法取得
🇺🇸 美股：+$890,123 TWD

合計：無法計算（部分資料缺失）
```

### Total failure — both markets unavailable

```
📈 投資組合未實現損益

無法取得損益資料，請稍後再試
```

### Negative PnL example

```
📈 投資組合未實現損益

🇹🇼 台股：-$123,456 TWD
🇺🇸 美股：+$890,123 TWD

合計：+$766,667 TWD
```

---

## Number Formatting Rules

- Format: `f'{value:+,.0f}'` — always shows sign (`+` or `-`), thousands comma, no decimals
- Currency suffix: ` TWD` on each line and total
- Zero: displays as `+$0 TWD`

---

## Webhook Endpoint Behaviour

Existing `POST /api/v1/webhook/telegram` handles `/pnl` in the command dispatch block.
No new endpoint. No change to response envelope:

```json
{"status": "success", "data": null, "message": "ok"}
```

---

## Telegram `setMyCommands` Entry

```json
{"command": "pnl", "description": "投資組合未實現損益（台股＋美股）"}
```

---

## Help Text Addition

New line added to `/help` reply:

```
/pnl — 投資組合未實現損益（台股＋美股）
```

---

## Data Sources

| Market | Env var | Cell | Row (0-idx) | Col (0-idx) |
|--------|---------|------|-------------|-------------|
| TW | `GOOGLE_SHEETS_PORTFOLIO_GID_TW` | I20 | 19 | 8 |
| US | `GOOGLE_SHEETS_PORTFOLIO_GID_US` | H21 | 20 | 7 |

Both values are in TWD. Sheet ID from `GOOGLE_SHEETS_ID`.
