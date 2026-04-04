<!-- SYNC IMPACT REPORT
Version change: 1.0.0 → 1.1.0
Modified principles:
  - III. API Consistency: removed stray embedded "## API Endpoints / Tasks" block (mis-pasted content);
    translated service-layer rule from Chinese to English.
  - IV. Performance & Resilience: added explicit cache-implementation constraint
    (redis-py required; custom TTL logic PROHIBITED).
Added sections: N/A
Removed sections: Stray "API Endpoints" block (not a constitution section).
Security Constraints: expanded hardcoded-secret prohibition to explicitly include IPs.
Governance: translated three Chinese-language rules and integrated them:
  - no-hardcode rule → already in Security Constraints (reinforced);
  - redis-py rule → added to Principle IV;
  - no-unilateral-constitution-edit rule → added to Governance procedure (step 1).
Templates requiring updates:
  ✅ .specify/memory/constitution.md (this file — updated)
  ✅ .specify/templates/plan-template.md (Constitution Check gate I–IV; no static update needed)
  ✅ .specify/templates/spec-template.md (Constraints field aligns with Principle IV; no update needed)
  ✅ .specify/templates/tasks-template.md (phase structure aligns with MVP-first workflow; no update needed)
Follow-up TODOs: None — all placeholders resolved.
-->

# fastApiStock Constitution

## Core Principles

### I. Code Quality (NON-NEGOTIABLE)

All production code MUST pass `ruff check` and `ruff format` and `mypy` strict type checking before merge.

- Every public function MUST have complete type hints and a Google-style docstring.
- `print()`, `eval()`, `exec()`, bare `except:`, and `Any` are PROHIBITED.
- Functions MUST NOT exceed 50 lines; each function has one clear responsibility.
- Hardcoded secrets (API keys, passwords, IPs) are PROHIBITED; all credentials MUST be loaded
  via `python-dotenv` from environment variables.
- `# noqa` suppressions require an explicit written justification comment.

**Rationale**: Type safety and enforced linting prevent entire classes of runtime errors and keep
the codebase maintainable as the feature set grows.

### II. Testing Standards

New features MUST include tests before they are considered complete. Target coverage is 80%+.

- Unit tests cover business logic in isolation (`tests/unit/`).
- Integration tests cover API routes end-to-end via `httpx` + `pytest` (`tests/integration/`).
- Test files mirror `src/` directory structure.
- The database or external layer MUST NOT be mocked when a real connection is available.
- Tests MUST be written before implementation (Red → Green → Refactor).

**Rationale**: A financial data API where incorrect output has real consequences demands a reliable
test safety net. Mock-heavy tests create false confidence.

### III. API Consistency

Every API response MUST follow the envelope:
`{ "status": "success"|"error", "data": {} | [], "message": "" }`.

- All routes MUST implement redis rate limiting at the router level with Redis 
- Error responses MUST use correct HTTP status codes (4xx = client error, 5xx = server error).
- Routes MUST be organized via `APIRouter`; no route definitions in `main.py`.
- HTTP 422 validation errors MUST surface as the standard envelope, not raw FastAPI detail.
- Business logic MUST NOT be placed in route handlers; it MUST be extracted to a service layer.

**Rationale**: Consistent response shapes let consumers write predictable parsing logic and reduce
integration bugs across different callers.

### IV. Performance & Resilience

External calls to TW stock data sources MUST include an explicit `timeout` and a random delay
(0.5–2 s) between successive requests.

- All fetched data MUST be cached by Redis to avoid redundant network calls.
- Caching MUST be implemented with `redis-py`; custom TTL logic is PROHIBITED.
- Cached endpoints SHOULD respond within 200 ms; live-fetch endpoints within 2 s.
- Every outgoing HTTP request MUST declare a `timeout` argument — no open-ended waits.

**Rationale**: TW stock data sources rate-limit aggressively; polite delays and redis-backed
caching protect availability, reduce ban risk, and keep response times predictable. Standardising
on redis-py prevents divergent home-grown TTL implementations.

## Security Constraints

- Secrets and credentials (API keys, DB passwords, IPs) MUST come from environment variables
  via `.env` + `python-dotenv`; hardcoding any of these in source code is PROHIBITED.
- SQL queries MUST use parameterized statements; string interpolation inside queries is PROHIBITED.
- Rate limiting MUST be applied at the router level — not ad-hoc per individual endpoint.
- `uv.lock` is the authoritative dependency lock; `requirements.txt` is export-only (never hand-edited).
- `conda install` is PROHIBITED for project production dependencies.

## Development Workflow

- **MVP first**: deliver the simplest working slice, validate, then iterate — no speculative abstractions.
- **KISS & YAGNI**: implement only what the current feature requires.
- Pre-commit hooks (Ruff, mypy, secrets scan) MUST pass before every `git commit`.
- Commit messages MUST follow Conventional Commits (`feat`, `fix`, `docs`, `test`, `chore`).
- No `--no-verify` bypasses; if a hook fails, fix the underlying issue.
- PRs require all CI checks to pass before merge.

## Governance

This constitution supersedes all conflicting local conventions. Amendments require:

1. A discussion (PR description or documented decision) stating the changed principle and motivation
   MUST precede any edit to `constitution.md`; unilateral undiscussed edits are PROHIBITED.
2. A version bump per semantic rules:
   - **MAJOR**: principle removal or incompatible redefinition.
   - **MINOR**: new principle or materially expanded guidance.
   - **PATCH**: clarification, wording, or non-semantic refinement.
3. All dependent templates MUST be reviewed and updated after ratification.
4. The Sync Impact Report (HTML comment at top of file) MUST be updated with every amendment.

All feature plans MUST include a Constitution Check gate that verifies compliance with Principles I–IV
before Phase 0 research begins and again after Phase 1 design.

**Version**: 1.1.0 | **Ratified**: 2026-04-03 | **Last Amended**: 2026-04-03
