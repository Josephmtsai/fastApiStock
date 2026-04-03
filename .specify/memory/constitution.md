<!-- SYNC IMPACT REPORT
Version change: (none) → 1.0.0
Added sections:
  - Core Principles I–IV (Code Quality, Testing Standards, API Consistency, Performance & Resilience)
  - Security Constraints
  - Development Workflow
  - Governance
Removed sections: N/A (initial authoring)
Templates requiring updates:
  - ✅ .specify/memory/constitution.md (this file)
  - ✅ .specify/templates/plan-template.md (Constitution Check gate references I–IV dynamically; no static update needed)
  - ✅ .specify/templates/spec-template.md (Performance Goals / Constraints fields align with Principle IV)
  - ✅ .specify/templates/tasks-template.md (task phases align with MVP-first strategy in Principle III / Workflow)
Follow-up TODOs: None — all placeholders resolved.
-->

# fastApiStock Constitution

## Core Principles

### I. Code Quality (NON-NEGOTIABLE)

All production code MUST pass `ruff check` and `ruff format` and `mypy` strict type checking before merge.

- Every public function MUST have complete type hints and a Google-style docstring.
- `print()`, `eval()`, `exec()`, bare `except:`, and `Any` are PROHIBITED.
- Functions MUST NOT exceed 50 lines; each function has one clear responsibility.
- Hardcoded secrets are PROHIBITED; all credentials MUST be loaded via `python-dotenv`.
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

Every API response MUST follow the envelope: `{ "status": "success"|"error", "data": {} | [], "message": "" }`.

- All routes MUST implement rate limiting at the router level.
- Error responses MUST use correct HTTP status codes (4xx = client error, 5xx = server error).
- Routes MUST be organized via `APIRouter`; no route definitions in `main.py`.
- HTTP 422 validation errors MUST surface as the standard envelope, not raw FastAPI detail.
- 業務邏輯不能寫在 route handler 中，必須抽到 service layer
## API Endpoints


### Tasks
| Method | Endpoint           | Description        
|--------|--------------------|--------------------
| GET    | /api/v1/tw_stock/{id} | Get stock info by IDs      




**Rationale**: Consistent response shapes let consumers write predictable parsing logic and reduce
integration bugs across different callers.

### IV. Performance & Resilience

External calls to TW stock data sources MUST include an explicit `timeout` and a random delay
(0.5–2 s) between successive requests.

- All fetched data MUST be cached locally to avoid redundant network calls.
- Cached endpoints SHOULD respond within 200 ms; live-fetch endpoints within 2 s.
- Every outgoing HTTP request MUST declare a `timeout` argument — no open-ended waits.

**Rationale**: TW stock data sources rate-limit aggressively; polite delays and local caching
protect availability, reduce ban risk, and keep response times predictable.

## Security Constraints

- Secrets (API keys, DB credentials) MUST come from environment variables via `.env` + `python-dotenv`.
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

1. A PR describing the changed principle and motivation.
2. A version bump per semantic rules:
   - **MAJOR**: principle removal or incompatible redefinition.
   - **MINOR**: new principle or materially expanded guidance.
   - **PATCH**: clarification, wording, or non-semantic refinement.
3. All dependent templates MUST be reviewed and updated after ratification.
- 禁止在程式碼中硬寫 IP/密碼/API key（一律用環境變數）
- 禁止自行實作快取機制（用 redis-py，不要自己寫 TTL 邏輯）
- 禁止在沒有討論的情況下更動 constitution.md

All feature plans MUST include a Constitution Check gate that verifies compliance with Principles I–IV
before Phase 0 research begins and again after Phase 1 design.



**Version**: 1.0.0 | **Ratified**: 2026-04-03 | **Last Amended**: 2026-04-03
