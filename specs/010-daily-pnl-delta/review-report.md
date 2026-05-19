# Code Review Report

**Feature**: 010-daily-pnl-delta
**Branch**: main
**Reviewed files**:

- `src/fastapistock/repositories/portfolio_snapshot_repo.py`
- `src/fastapistock/scheduler.py`
- `src/fastapistock/services/portfolio_service.py`
- `src/fastapistock/services/telegram_service.py`
- `tests/test_portfolio_service.py`
- `tests/test_portfolio_snapshot_repo.py`
- `tests/test_scheduler.py`

**Date**: 2026-05-19

## Summary

PASS

## Issues Found

| File | Line | Severity | Issue |
| --- | --- | --- | --- |
| `src/fastapistock/scheduler.py` | previous trading-date helpers | INFO | Initial review found weekend handling was missing for previous-close lookup. Developer added weekday-skip logic and regression tests. |
| `src/fastapistock/services/portfolio_service.py` | `format_market_daily_pnl_delta` unavailable-current branch | INFO | Follow-up review found unavailable current PnL could be shown as `+0 TWD` or a partial total in the old total formatter. Developer replaced the formatter with market-specific output and added regression tests so unavailable current PnL is reported explicitly. |
| `src/fastapistock/scheduler.py` | `_scheduled_push` | INFO | Requirement changed from cross-market total comparison to active-market-only comparison. Developer updated scheduler calls so TW pushes request TW deltas and US pushes request US deltas. |

## Project Rule Violations

- No blocking rule violations found.
- Latest market-specific implementation still needs final QA validation after
  full formatting, test, and pre-commit runs.

## Recommendation

PASS: safe to use `fastapistock-qa`.
