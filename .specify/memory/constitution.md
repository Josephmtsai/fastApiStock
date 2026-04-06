<!-- SYNC IMPACT REPORT
Version change: 1.1.0 → 1.2.0
Modified principles:
  - I. Code Quality: expanded no-hardcode rule to cover ALL configuration values
    (timeouts, thresholds, URLs, feature flags) — not just secrets.
  - IV. Performance & Resilience: added graceful-fallback requirement (Redis/dependency
    down → degrade, never hang); reinforced Redis-first caching — introducing parallel
    caching mechanisms (file-based, in-memory TTL wrappers) is PROHIBITED.
Added sections:
  - V. Observability: structured request/response logging with a mandatory format
    (DateTime ProcessId Method ClientIP HTTP_METHOD Payload).
Modified sections:
  - Development Workflow: added explicit "no reinventing the wheel" rule — reuse
    established project patterns (Redis caching) before introducing new solutions.
  - Governance: Constitution Check gate updated from I–IV to I–V.
Security Constraints: no change.
Templates requiring updates:
  ✅ .specify/templates/plan-template.md (generic gate — no hardcoded numeral to update)
  ✅ .specify/memory/constitution.md (this file — updated)
  ✅ .specify/templates/spec-template.md (no update needed)
  ✅ .specify/templates/tasks-template.md (no update needed)
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
- Configuration values (timeouts, rate-limit thresholds, URLs, port numbers, feature flags)
  MUST be externalised to environment variables or a dedicated config module; literal magic
  numbers embedded in business logic are PROHIBITED.
- `# noqa` suppressions require an explicit written justification comment.

**Rationale**: Type safety and enforced linting prevent entire classes of runtime errors and keep
the codebase maintainable as the feature set grows. Externalising configuration ensures
environment-specific tuning without code changes and makes values auditable in one place.

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
  Introducing parallel caching mechanisms (file-based JSON, in-memory TTL wrappers) alongside
  Redis is PROHIBITED — one caching layer, one source of truth.
- When Redis or any external dependency is unavailable, the service MUST degrade gracefully
  (e.g., skip cache and fetch live, or return a stale marker) — APIs MUST NOT hang, crash,
  or return a 5xx solely because a cache backend is unreachable.
- All external dependency clients (Redis, HTTP) MUST be configured with connect/read timeouts;
  open-ended waits are PROHIBITED.
- Cached endpoints SHOULD respond within 200 ms; live-fetch endpoints within 2 s.
- Every outgoing HTTP request MUST declare a `timeout` argument — no open-ended waits.

**Rationale**: TW stock data sources rate-limit aggressively; polite delays and redis-backed
caching protect availability, reduce ban risk, and keep response times predictable. Standardising
on redis-py prevents divergent home-grown TTL implementations. Graceful fallback ensures a
single dependency failure never takes the entire API offline.

### V. Observability

Every API endpoint MUST produce structured request and response log entries via Python `logging`
(never `print()`). Two log categories are required:

**Request / Response Log** — traces every call from input to output:

```
{DateTime} {ProcessId} {Method} {ClientIP} {HTTP_METHOD} REQ {RequestData}
{DateTime} {ProcessId} {Method} {ClientIP} {HTTP_METHOD} RES {StatusCode} {ResponseData}
```

**Performance Log** — measures handler latency:

```
{DateTime} {ProcessId} {Method} PERF {ResponseTimeMs}ms
```

Field definitions:

- `DateTime`: ISO 8601 with milliseconds (e.g. `2026-04-06T14:30:00.123`).
- `ProcessId`: OS process ID for multi-worker correlation.
- `Method`: The handler or service function name (e.g. `get_stock_quotes`).
- `ClientIP`: `request.client.host` (or `X-Forwarded-For` behind a proxy).
- `HTTP_METHOD`: `GET`, `POST`, etc.
- `RequestData`: Query params, path params, or body (sensitive fields MUST be masked).
- `ResponseData`: Abbreviated payload (truncate large `data` arrays to keep logs readable).
- `ResponseTimeMs`: Wall-clock time from request received to response sent, in milliseconds.

Implementation requirements:

- Logging MUST be implemented as a **middleware** — not duplicated in every route handler.
  A single middleware produces all three log lines (REQ, RES, PERF) per request.
- Log level: `INFO` for normal requests; `WARNING` for 4xx; `ERROR` for 5xx.
  Performance lines are always `INFO`.
- The log format MUST be configured centrally (e.g. `logging.config` or a shared formatter);
  individual modules MUST NOT define their own format strings.

**Rationale**: Consistent, structured logs are essential for debugging production issues,
monitoring latency, and auditing access. A fixed format enables log aggregation tools
(ELK, Loki, CloudWatch) to parse and index fields automatically. A dedicated performance
line makes it trivial to alert on slow endpoints without parsing the full response log.

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
- **No reinventing the wheel**: before introducing a new library or custom mechanism, verify
  whether an established project pattern already solves the problem (e.g. Redis for caching,
  `slowapi` for rate limiting). Duplicating functionality that already exists in the stack is
  PROHIBITED.
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

All feature plans MUST include a Constitution Check gate that verifies compliance with Principles I–V
before Phase 0 research begins and again after Phase 1 design.

**Version**: 1.2.0 | **Ratified**: 2026-04-03 | **Last Amended**: 2026-04-06
