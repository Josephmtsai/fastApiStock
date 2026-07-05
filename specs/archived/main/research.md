# Research: Portfolio PnL Command (`/pnl`)

**Date**: 2026-04-11
**Feature**: Add `/pnl` Telegram bot command showing total unrealized PnL for TW and US portfolios.

## Decisions

| Topic | Decision | Rationale | Alternatives Considered |
|-------|----------|-----------|------------------------|
| Cell-reading strategy | CSV export + row/col index constants | Reuses existing `_SHEETS_CSV_URL` + `_parse_number()` helpers; no new credentials needed | Sheets API v4 (**rejected** — requires OAuth/service account not present), named ranges (**rejected** — requires sheet owner setup) |
| Caching | Redis with `PORTFOLIO_CACHE_TTL`, keys `pnl:tw:{date}` / `pnl:us:{date}` | Constitution IV mandates Redis-only caching; matches `investment_plan_repo.py` pattern | No cache (**rejected** — violates IV), in-memory TTL (**prohibited** by constitution) |
| Formatting location | New `portfolio_service.py` | Constitution III: business logic belongs in service layer; clean domain separation | Inline in `webhook.py` (**rejected** — violates III) |
| Failure handling | Return `float \| None`; show `無法取得` per market | Constitution IV: graceful degradation; partial data still useful | Raise exception (**rejected** — bot would crash or return 500) |
| Number format | `f'{value:+,.0f} TWD'` | Shows direction (+/-) explicitly; no decimals needed for TWD totals | Plain integer (**rejected** — no sign), 2 decimals (**rejected** — unnecessary for TWD) |

## Resolved Unknowns

| Unknown | Resolution |
|---------|-----------|
| Are I20 / H21 always present? | Yes — formula-driven summary cells at fixed positions. Returns `None` if row/col out of range. |
| Could values be blank? | `_parse_number()` already returns `0.0` for blank — existing helper handles this. |
| Comma-formatted numbers? | `_parse_number()` strips commas before `float()` — already handled. |
| Does `GOOGLE_SHEETS_PORTFOLIO_GID_TW` fall back? | Yes — falls back to `GOOGLE_SHEETS_PORTFOLIO_GID` in `config.py`. |

## Key Findings

1. **Reuse `_parse_number()`** from `portfolio_repo.py` — handles blanks, commas, and negatives.
2. **Reuse `_SHEETS_CSV_URL`** — same CSV export URL pattern already used for TW and US portfolio.
3. **Follow `investment_plan_repo.py` caching pattern** — Redis try → miss → fetch live → store back.
4. **Cell indices**: TW I20 = row 19, col 8; US H21 = row 20, col 7 (both 0-indexed).
