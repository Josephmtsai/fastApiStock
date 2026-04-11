# Tasks: Portfolio PnL Command (`/pnl`)

**Input**: Design documents from `specs/main/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/pnl-command.md ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm project wiring and existing helpers before adding new code.

- [ ] T001 Read `src/fastapistock/repositories/portfolio_repo.py` to understand `_SHEETS_CSV_URL`, `_parse_number()`, and the Redis caching pattern used by `investment_plan_repo.py`
- [ ] T002 Read `src/fastapistock/routers/webhook.py` to locate command dispatch block and `_HELP_TEXT`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core building blocks required before both user stories can proceed.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 Add row/col constants `_TW_PNL_ROW = 19`, `_TW_PNL_COL = 8`, `_US_PNL_ROW = 20`, `_US_PNL_COL = 7` to `src/fastapistock/repositories/portfolio_repo.py`

**Checkpoint**: Constants in place — repo functions and service can now be implemented in parallel.

---

## Phase 3: User Story 1 — Developer can navigate source code intuitively (Priority: P1) 🎯 MVP

**Goal**: Add `/pnl` command implementation following the repository → service → router layering so any developer can locate each concern in the conventional location.

**Independent Test**: Send `POST /api/v1/webhook/telegram` with `{"text": "/pnl"}` and a valid secret header. Bot sends a formatted PnL reply to the chat. Run `uv run uvicorn src.fastapistock.main:app --reload` — no import errors.

### Implementation for User Story 1

- [ ] T004 [P] [US1] Implement `fetch_pnl_tw() -> float | None` in `src/fastapistock/repositories/portfolio_repo.py` — Redis cache key `pnl:tw:{YYYY-MM-DD}`, TTL `PORTFOLIO_CACHE_TTL`, reads row 19 col 8 via `_SHEETS_CSV_URL` + `GOOGLE_SHEETS_PORTFOLIO_GID_TW`, uses `_parse_number()`
- [ ] T005 [P] [US1] Implement `fetch_pnl_us() -> float | None` in `src/fastapistock/repositories/portfolio_repo.py` — Redis cache key `pnl:us:{YYYY-MM-DD}`, TTL `PORTFOLIO_CACHE_TTL`, reads row 20 col 7 via `_SHEETS_CSV_URL` + `GOOGLE_SHEETS_PORTFOLIO_GID_US`, uses `_parse_number()`
- [ ] T006 [US1] Create `src/fastapistock/services/portfolio_service.py` — implement `_format_pnl_reply(tw_pnl: float | None, us_pnl: float | None) -> str` (pure function, number format `f'{value:+,.0f}'`, handles both-available / partial / both-failed cases per contract)
- [ ] T007 [US1] Add `get_pnl_reply() -> str` to `src/fastapistock/services/portfolio_service.py` — orchestrates `fetch_pnl_tw()` + `fetch_pnl_us()` then delegates to `_format_pnl_reply()`
- [ ] T008 [US1] Add `/pnl` dispatch branch to command block in `src/fastapistock/routers/webhook.py` — call `get_pnl_reply()`, pass result to `reply_to_chat(chat_id, reply)`
- [ ] T009 [US1] Add `/pnl — 投資組合未實現損益（台股＋美股）` to `_HELP_TEXT` in `src/fastapistock/routers/webhook.py`

**Checkpoint**: `/pnl` command fully routed through repo → service → router. Test with curl from quickstart.md.

---

## Phase 4: User Story 2 — Tests are co-located and easy to run (Priority: P2)

**Goal**: Ensure `uv run pytest` discovers and passes unit tests for the new repo functions and service formatting logic with no configuration changes.

**Independent Test**: `uv run pytest --co -q` lists `test_portfolio_repo_pnl.py` and `test_portfolio_service.py` without errors. `uv run pytest tests/test_portfolio_repo_pnl.py tests/test_portfolio_service.py` all pass.

### Implementation for User Story 2

- [ ] T010 [P] [US2] Create `tests/test_portfolio_repo_pnl.py` — unit tests for `fetch_pnl_tw()` and `fetch_pnl_us()` using `unittest.mock`: Redis cache hit (returns cached float), Redis miss → httpx success (parses row/col, caches result), httpx error (returns None), row out of range (returns None)
- [ ] T011 [P] [US2] Create `tests/test_portfolio_service.py` — unit tests for `_format_pnl_reply()`: both values positive, one value None (partial failure message), both None (total failure message), negative TW value with positive US value, zero value shows `+$0 TWD`

**Checkpoint**: `uv run pytest` passes. `uv run pytest --cov=src --cov-report=term-missing` shows ≥ 80% coverage on new files.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and quality gates.

- [ ] T012 [P] Run `uv run ruff check . --fix && uv run ruff format .` and fix any remaining lint errors in modified files
- [ ] T013 [P] Run `uv run mypy src/` and resolve any type errors in `portfolio_repo.py`, `portfolio_service.py`, and `webhook.py`
- [ ] T014 Run `uv run pre-commit run --all-files` — all hooks must pass before commit
- [ ] T015 Run quickstart.md validation: health check, then `/pnl` webhook curl against local server to confirm end-to-end reply

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (must read existing code before adding constants)
- **User Story 1 (Phase 3)**: Depends on Phase 2 (constants must exist) — T004 and T005 can run in parallel; T006 before T007; T008 and T009 depend on T007
- **User Story 2 (Phase 4)**: Depends on Phase 3 completion (tests exercise the real implementations)
- **Polish (Phase 5)**: Depends on all stories complete

### Within User Story 1

```
T003 (constants)
  ├── T004 [P] fetch_pnl_tw()
  └── T005 [P] fetch_pnl_us()
        └── T006 _format_pnl_reply()
              └── T007 get_pnl_reply()
                    ├── T008 webhook dispatch
                    └── T009 help text
```

### Parallel Opportunities

```bash
# Phase 3 — after T003, launch repo functions together:
Task: T004  # fetch_pnl_tw in portfolio_repo.py
Task: T005  # fetch_pnl_us in portfolio_repo.py

# Phase 4 — after Phase 3, launch test files together:
Task: T010  # test_portfolio_repo_pnl.py
Task: T011  # test_portfolio_service.py

# Phase 5 — polish can run in parallel:
Task: T012  # ruff
Task: T013  # mypy
```

---

## Implementation Strategy

### MVP (Minimum Viable /pnl)

1. Complete Phase 1: Read existing code
2. Complete Phase 2: Add constants
3. Complete Phase 3: Implement repo → service → router
4. **STOP and VALIDATE**: Curl the `/pnl` webhook endpoint locally
5. Add tests (Phase 4) before committing

### Incremental Delivery

1. Phase 1 + 2 → understand codebase, add constants
2. Phase 3 → `/pnl` command works end-to-end
3. Phase 4 → tests pass, coverage ≥ 80%
4. Phase 5 → pre-commit green, ready to commit

---

## Notes

- [P] tasks operate on different files — safe to implement in parallel
- `_format_pnl_reply` is a pure function — write and test it before wiring `get_pnl_reply()`
- Do **not** add a new cache mechanism; reuse `PORTFOLIO_CACHE_TTL` and the existing Redis pattern from `investment_plan_repo.py`
- Number format rule: `f'{value:+,.0f}'` — sign always shown, no decimals, thousands comma
- `GOOGLE_SHEETS_PORTFOLIO_GID_TW` falls back to `GOOGLE_SHEETS_PORTFOLIO_GID` in `config.py` — verify before writing the env-var read
