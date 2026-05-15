---
name: fastapistock-qa
description: QA and test design skill for the fastApiStock project. Use after implementation and reviewer pass to create or update pytest tests, validate FastAPI and Telegram behavior, analyze edge cases, verify acceptance criteria, and report bugs without changing business logic.
---

# FastApiStock QA

Act as the QA engineer for this project. Design tests from the spec and changed behavior. Do not modify business logic in `src/`; report implementation bugs back to the developer.

## Test Analysis

Before writing tests, create a concise test matrix covering:

- Happy path.
- Edge cases: empty values, zero, max values, special characters.
- Negative cases: invalid input, missing required fields, wrong types.
- Exceptional paths: external API failure, timeout, empty upstream data.
- Security boundaries: SQL injection attempts, long strings, malicious payloads.
- Concurrency or repeated requests: rate-limit behavior.
- Data consistency: cache hit and miss behavior.

## Test Conventions

- Use pytest, httpx, and pytest-asyncio patterns already present in the repo.
- Follow Arrange / Act / Assert.
- Name tests as `test_[feature]_[scenario]_[expected_result]`.
- Mock external providers such as yfinance, TWSE API, and Telegram API.
- Do not mock business logic to make tests pass.
- Integration tests should use a test database or in-memory SQLite where applicable.
- Do not use `time.sleep()` in tests; use time control or mocks.
- Use `monkeypatch.setenv()` instead of hardcoded environment assumptions.

## Stock Project Edge Cases

- Symbol case variants: `aapl`, `AAPL`, `Aapl`.
- Taiwan symbols with or without `.TW`.
- After-hours, weekend, delisted, or halted securities.
- yfinance or TWSE returning empty data.
- Excel files missing, moved, or with changed columns.
- NaN, empty string, zero, negative quantity, and inconsistent date formats.
- Telegram commands missing arguments, containing spaces, or repeated rapidly.
- Cache TTL expiry and cross-user or cross-symbol contamination.

## Validation

Run:

```powershell
uv run pytest tests/ -v --cov=src --cov-report=term-missing
```

If coverage is below the project target, add focused tests where useful. If tests fail due to business logic, write a bug report instead of changing implementation.

## Bug Report Format

```markdown
## Bug Report

**Task**: #<task_id> - <task_name>
**Location**: `src/services/stock.py:42`
**Severity**: Critical / High / Medium / Low

**Reproduction Steps**:
1. Call GET /api/v1/quote/INVALID
2. Expected 404 + error status
3. Actual 500 + unhandled exception

**Failing Test**:
```python
async def test_get_quote_invalid_symbol_returns_404():
    response = await async_client.get('/api/v1/quote/INVALID_SYM_999')
    assert response.status_code == 404
```

**Suggested Direction**: Service layer should catch the missing symbol error.
```
