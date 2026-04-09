# Feature Specification: US Portfolio Sheets Integration

**Feature Branch**: `002-us-portfolio-sheets`
**Created**: 2026-04-09
**Status**: Draft
**Context**: Extend personal portfolio enrichment to US stock Telegram pushes using a dedicated US route and existing US scheduler flow, while keeping Redis-first caching, graceful fallback, and structured logging.

## Overview

Users maintain US holdings in Google Sheets and the system appends portfolio fields to each US stock block in Telegram messages.

- US API route is independent: `GET /api/v1/usMessage/{id}`
- US scheduler flow is independent in service logic: `push_us_stocks()`
- Google Sheet source uses the same sheet ID as other portfolio data, but US data is read from dedicated env-configured GID (example value: `320283463`)
- US column mapping: `A=symbol_with_prefix`, `F=shares`, `G=avg_cost`, `H=unrealized_pnl`

Data is fetched from Google Sheets CSV export URL (public share link; no OAuth/API key).

## User Scenarios & Testing

### User Story 1 - US push includes portfolio block (Priority: P1)

A user receiving US Telegram pushes can see `avg_cost` and `unrealized_pnl` inline for held symbols without opening Sheets.

**Why this priority**: This is the core business value for US portfolio personalization.

**Independent Test**: Trigger `GET /api/v1/usMessage/{id}?stock=AAPL,TSLA`; for symbols existing in US portfolio sheet, Telegram message includes the portfolio block. For symbols not found, technical indicators still show and message sending still succeeds.

**Acceptance Scenarios**:

1. **Given** sheet row `US_AAPL` has `F=10`, `G=180.00`, `H=12000`, **When** pushing `AAPL`, **Then** portfolio block is shown.
2. **Given** symbol is absent in sheet, **When** pushing that symbol, **Then** no portfolio block is rendered for that symbol.
3. **Given** Sheets is unreachable, **When** US push runs, **Then** message still sends with technical indicators and portfolio block is skipped silently.

---

### User Story 2 - US portfolio cache minimizes repeated fetches (Priority: P2)

Repeated US pushes inside TTL should avoid duplicate Sheets fetches via Redis cache.

**Why this priority**: Reduces external request load and improves latency.

**Independent Test**: Trigger two US pushes within TTL; logs show first fetch from Sheets and second cache hit.

**Acceptance Scenarios**:

1. **Given** cache hit, **When** US push runs, **Then** no new Sheets HTTP request is made.
2. **Given** cache TTL expired, **When** US push runs, **Then** sheet is fetched again and cache refreshed.
3. **Given** Redis unavailable, **When** US push runs, **Then** live Sheets fetch is used (fallback), without crashing the API/job.

---

### Edge Cases

- US symbol in `A` includes prefix/separator: `US_AAPL`, `NASDAQ:AAPL`, `NYSE-MSFT` -> normalized ticker must match (`AAPL`, `MSFT`).
- Non-symbol or malformed rows (subtotal/blank/formula noise) are skipped silently.
- `H` value with comma/negative sign (e.g., `-75,000`) is parsed correctly.
- Sheet not public or request timeout returns empty portfolio snapshot and logs warning/error.
- Multi-symbol push where only partial matches exist renders portfolio block only for matched symbols.

## Requirements

### Functional Requirements

- **FR-001**: System MUST read US portfolio data from public Google Sheets CSV export URL (no OAuth/API key).
- **FR-002**: US portfolio data MUST use same sheet ID and dedicated env var `GOOGLE_SHEETS_PORTFOLIO_GID_US` (example value: `320283463`).
- **FR-003**: US column mapping MUST be fixed as:
  - `A`: symbol with English prefix
  - `F`: shares
  - `G`: average cost
  - `H`: unrealized PnL
- **FR-004**: Symbol matching MUST normalize `A` by removing leading alphabetic prefix and separators, then compare by normalized ticker (e.g., `US_AAPL` -> `AAPL`).
- **FR-005**: System MUST append portfolio block per US symbol when matched.
- **FR-006**: Portfolio block MUST include average cost, unrealized PnL, and price-vs-cost percentage.
- **FR-006a**: US unrealized PnL unit MUST be rendered as `USD` in Telegram message.
- **FR-007**: US portfolio data MUST use Redis cache only; TTL MUST come from env/config.
- **FR-008**: All operational values (sheet ID, TW/US gid, timeout, TTL, cache keys) MUST come from env/config and MUST NOT be hardcoded in business logic.
- **FR-009**: On Sheets fetch failure, system MUST degrade gracefully: skip portfolio block and continue normal US push.
- **FR-010**: On Redis failure, system MUST degrade to live fetch and MUST NOT block API response/scheduler flow.
- **FR-011**: Requests and responses MUST continue using standardized envelope/logging conventions; additional cache/fallback events SHOULD be logged for observability.
- **FR-012**: US API and TW API remain separate endpoints; implementation MUST NOT merge routes.
- **FR-013**: US scheduler flow remains in US path (`push_us_stocks`) and MUST NOT rely on TW-only service function.

### Key Entities

- **USPortfolioEntry**: Single US holding (`normalized_symbol`, `avg_cost`, `unrealized_pnl`).
- **USPortfolioSnapshot**: Map of normalized ticker to `USPortfolioEntry`.
- **SymbolNormalizer**: Rule set that strips prefix/separator and uppercases ticker.

## Success Criteria

### Measurable Outcomes

- **SC-001**: For US symbols with sheet entries, portfolio block display accuracy is 100%.
- **SC-002**: Sheets/Redis failures do not break US push delivery.
- **SC-003**: Within TTL, repeated US pushes cause at most one Sheets fetch per cache cycle.
- **SC-004**: Negative/comma-formatted PnL parsing accuracy is 100%.
- **SC-005**: Cache-hit path adds minimal overhead (target < 10 ms for portfolio enrichment segment).

## Assumptions

- Google Sheets is public-readable by link.
- First row is header; data starts from second row.
- Sheet formulas precompute unrealized PnL.
- Existing US route (`/api/v1/usMessage/{id}`) and scheduler US flow are kept.
- `GOOGLE_SHEETS_PORTFOLIO_GID_US` is configured in environment for US holdings tab.
- TTL and timeout defaults are defined in config and overridable by env.

## Out Of Scope

- Writing back to Sheets (read-only integration).
- Automatic column autodetection (column positions fixed by contract).
- Portfolio history tracking and alerting.
- Unifying TW and US into one endpoint.
