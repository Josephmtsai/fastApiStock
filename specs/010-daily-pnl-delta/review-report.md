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
| `src/fastapistock/services/portfolio_service.py` | `format_daily_pnl_delta` missing-baseline branch | INFO | Follow-up review found unavailable current PnL could be shown as `+0 TWD` or a partial total. Developer added regression tests and now reports current total unavailable unless both current TW and US PnL are present. |

## Project Rule Violations

- No blocking rule violations found.
- `uv run pre-commit run --all-files` fails only on `no-commit-to-branch`
  because the workspace is currently on the protected `main` branch. Ruff,
  ruff-format, mypy, JSON/YAML/TOML checks, merge-conflict check, large-file
  check, and private-key detection all passed.

## Recommendation

PASS: safe to use `fastapistock-qa`.
