# Graph Report - .  (2026-05-08)

## Corpus Check
- 139 files · ~146,041 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1378 nodes · 3263 edges · 48 communities detected
- Extraction: 58% EXTRACTED · 42% INFERRED · 0% AMBIGUOUS · INFERRED: 1361 edges (avg confidence: 0.62)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_History Command & Inline Keyboards|History Command & Inline Keyboards]]
- [[_COMMUNITY_Schema & Service Layer|Schema & Service Layer]]
- [[_COMMUNITY_Portfolio & App Core|Portfolio & App Core]]
- [[_COMMUNITY_Investment Plan Repository|Investment Plan Repository]]
- [[_COMMUNITY_Test Fixtures & Fakes|Test Fixtures & Fakes]]
- [[_COMMUNITY_Rate Limiting Config|Rate Limiting Config]]
- [[_COMMUNITY_Report Pipeline Tests|Report Pipeline Tests]]
- [[_COMMUNITY_History Backfill CLI|History Backfill CLI]]
- [[_COMMUNITY_Database Engine & Session|Database Engine & Session]]
- [[_COMMUNITY_Investment Achievement Report|Investment Achievement Report]]
- [[_COMMUNITY_Portfolio PnL Repository|Portfolio PnL Repository]]
- [[_COMMUNITY_Signal History Redis Repo|Signal History Redis Repo]]
- [[_COMMUNITY_Sheets Archive Writer|Sheets Archive Writer]]
- [[_COMMUNITY_Report Builder Tests|Report Builder Tests]]
- [[_COMMUNITY_Stock Message Formatter|Stock Message Formatter]]
- [[_COMMUNITY_Portfolio Snapshot Repo|Portfolio Snapshot Repo]]
- [[_COMMUNITY_Webhook Auth Tests|Webhook Auth Tests]]
- [[_COMMUNITY_Cost Signal Persistence|Cost Signal Persistence]]
- [[_COMMUNITY_Callback & Keyboard Handlers|Callback & Keyboard Handlers]]
- [[_COMMUNITY_US Stock Service Tests|US Stock Service Tests]]
- [[_COMMUNITY_US Stock Repo Tests|US Stock Repo Tests]]
- [[_COMMUNITY_Webhook Integration Tests|Webhook Integration Tests]]
- [[_COMMUNITY_Reports Router Tests|Reports Router Tests]]
- [[_COMMUNITY_Alembic DB Migration|Alembic DB Migration]]
- [[_COMMUNITY_Telegram Update Models|Telegram Update Models]]
- [[_COMMUNITY_Backfill CLI Scripts|Backfill CLI Scripts]]
- [[_COMMUNITY_Webhook Security Design|Webhook Security Design]]
- [[_COMMUNITY_Webhook Startup Decision|Webhook Startup Decision]]
- [[_COMMUNITY_Module Initializer|Module Initializer]]
- [[_COMMUNITY_Technical Indicators|Technical Indicators]]
- [[_COMMUNITY_Transactions Repository|Transactions Repository]]
- [[_COMMUNITY_Scheduler Architecture|Scheduler Architecture]]
- [[_COMMUNITY_Response Envelope|Response Envelope]]
- [[_COMMUNITY_Redis Cache Layer|Redis Cache Layer]]
- [[_COMMUNITY_Bot Command Spec|Bot Command Spec]]
- [[_COMMUNITY_Railway CICD|Railway CI/CD]]
- [[_COMMUNITY_Webhook Secret Config|Webhook Secret Config]]
- [[_COMMUNITY_Sheets GID Config|Sheets GID Config]]
- [[_COMMUNITY_Bot Menu Registration|Bot Menu Registration]]
- [[_COMMUNITY_Progress Bar Format|Progress Bar Format]]
- [[_COMMUNITY_Unauthorized User Filter|Unauthorized User Filter]]
- [[_COMMUNITY_TW Signal Thresholds|TW Signal Thresholds]]
- [[_COMMUNITY_US Signal Thresholds|US Signal Thresholds]]
- [[_COMMUNITY_Investment Target Config|Investment Target Config]]
- [[_COMMUNITY_DB Engine File|DB Engine File]]
- [[_COMMUNITY_Database URL Config|Database URL Config]]
- [[_COMMUNITY_Sheets Auth Config|Sheets Auth Config]]
- [[_COMMUNITY_Dev Setup Guide|Dev Setup Guide]]

## God Nodes (most connected - your core abstractions)
1. `SymbolSnapshot` - 154 edges
2. `ReportSummary` - 146 edges
3. `PortfolioSnapshot` - 130 edges
4. `SignalRecord` - 119 edges
5. `RichStockData` - 71 edges
6. `PortfolioEntry` - 69 edges
7. `StockData` - 46 edges
8. `format_rich_stock_message()` - 37 edges
9. `StockNotFoundError` - 36 edges
10. `run_report_pipeline()` - 33 edges

## Surprising Connections (you probably didn't know these)
- `Integration tests for ``run_report_pipeline``.  These tests use the in-memory` --uses--> `PortfolioEntry`  [INFERRED]
  tests\test_report_pipeline_integration.py → src\fastapistock\repositories\portfolio_repo.py
- `Minimal stand-in matching the duck-typed ``RichStockData.price`` use.` --uses--> `PortfolioEntry`  [INFERRED]
  tests\test_report_pipeline_integration.py → src\fastapistock\repositories\portfolio_repo.py
- `Yield a chain of context-manager patches for both cron paths.` --uses--> `PortfolioEntry`  [INFERRED]
  tests\test_report_pipeline_integration.py → src\fastapistock\repositories\portfolio_repo.py
- `Weekly cron path: Postgres rows persisted + Telegram mock called once.` --uses--> `PortfolioEntry`  [INFERRED]
  tests\test_report_pipeline_integration.py → src\fastapistock\repositories\portfolio_repo.py
- `Monthly path must call sheet_writer.append_monthly_history twice.` --uses--> `PortfolioEntry`  [INFERRED]
  tests\test_report_pipeline_integration.py → src\fastapistock\repositories\portfolio_repo.py

## Hyperedges (group relationships)
- **Feature Progression 003→004→005→006** — spec003_feature, spec004_cost_level_signal, spec005_signal_history, spec006_report_history_postgres [EXTRACTED 0.95]
- **Webhook Command Dispatch Pipeline (/q /us /tw /pnl /history /help)** — arch_webhook_router, spec003_command_q, spec003_command_us, spec003_command_tw, main_pnl_command, spec003_command_help, spec006_history_command_inline [EXTRACTED 0.95]
- **Redis Caching Pattern (investment_plan, pnl, signal, options)** — spec003_investment_plan_cache_key, main_pnl_cache_key, spec005_signal_redis_key, spec006_history_options_api, arch_redis_cache [INFERRED 0.85]
- **Report Pipeline: Telegram→Postgres→Sheet (run_report_pipeline)** — spec006_run_report_pipeline, arch_telegram_service, spec006_report_history_repo, spec006_sheet_writer, spec006_run_report_result [EXTRACTED 0.95]
- **RichStockData Consumers (stock_service, us_stock_service, telegram_service)** — arch_rich_stock_data, arch_stock_service, arch_us_stock_service, arch_telegram_service, spec004_week52_high_field, spec004_ma50_field [INFERRED 0.85]
- **Postgres Persistence Group (report_history_repo, db/engine, alembic)** — spec006_report_history_repo, spec006_db_engine, spec006_db_models, spec006_alembic, arch_postgres [EXTRACTED 0.95]

## Communities

### Community 0 - "History Command & Inline Keyboards"
Cohesion: 0.02
Nodes (213): Recalculate pnl_tw_delta and pnl_us_delta from existing DB summary rows., Telegram ``/history`` command + inline-keyboard interaction (spec-006 D).  The, Resolve ``(symbol, market)`` and load the per-symbol monthly series.      When, Dispatch a parsed ``callback_query`` to the appropriate keyboard step.      Al, Render the market-selection menu (after type pick)., Branch to period menu (summary path) or symbol menu (symbol path)., Render the per-market symbol picker, sourcing options from the repo., Render the period menu after a symbol pick (symbol flow). (+205 more)

### Community 1 - "Schema & Service Layer"
Cohesion: 0.03
Nodes (96): BaseModel, Pydantic schemas for the stock domain., Full technical-analysis snapshot used by the scheduler and rich API endpoints., Real-time stock snapshot returned by GET /api/v1/stock/{id}.      Attributes:, RichStockData, StockData, answer_callback_query(), _build_price_change_lines() (+88 more)

### Community 2 - "Portfolio & App Core"
Cohesion: 0.02
Nodes (128): Google Sheets (External), services/history_handler.py, repositories/investment_plan_repo.py, services/investment_plan_service.py, middleware/logging.py LoggingMiddleware, main.py FastAPI App + Lifespan, PortfolioEntry (repositories/portfolio_repo.py), repositories/portfolio_repo.py (+120 more)

### Community 3 - "Investment Plan Repository"
Cohesion: 0.04
Nodes (78): _dict_to_entry(), _entry_to_dict(), fetch_investment_plan(), _fetch_live(), _parse_date(), _parse_number(), Repository for reading quarterly investment plan data from Google Sheets CSV exp, Serialise an InvestmentPlanEntry to a JSON-safe dict for Redis.      Args: (+70 more)

### Community 4 - "Test Fixtures & Fakes"
Cohesion: 0.05
Nodes (82): _repair_deltas(), db_session(), _fake_redis(), Shared pytest fixtures for the fastapistock test suite., Render ``BigInteger`` as ``INTEGER`` for SQLite so rowid autoincrement works., Replace all Redis clients with in-memory fakeredis instances.      Patches the, Yield a SQLite in-memory session isolated from production singletons.      The, _sqlite_bigint_as_integer() (+74 more)

### Community 5 - "Rate Limiting Config"
Cohesion: 0.06
Nodes (40): load_config(), _optional_int(), RateLimitConfig, Rate limit configuration loaded from environment variables.  Each route group, Immutable rate limit parameters for one route group.      Attributes:, Parse an optional integer env var.      Args:         env_name: Environment v, Build a ``RateLimitConfig`` from environment variables.      Args:         pr, Parse TW_STOCKS env var into a list of Taiwan stock codes.      Returns: (+32 more)

### Community 6 - "Report Pipeline Tests"
Cohesion: 0.06
Nodes (48): run_report_pipeline(), RunReportResult, _FakePrice, _common_patches(), _FakePrice, Integration tests for ``run_report_pipeline``.  These tests use the in-memory, Monthly path must call sheet_writer.append_monthly_history twice., Minimal stand-in matching the duck-typed ``RichStockData.price`` use. (+40 more)

### Community 7 - "History Backfill CLI"
Cohesion: 0.07
Nodes (58): _backfill_month(), _build_parser(), _build_tw_name_to_code(), _build_tw_snapshots(), _build_us_snapshots(), _fetch_close_price(), _fetch_usd_twd_rate(), main() (+50 more)

### Community 8 - "Database Engine & Session"
Cohesion: 0.06
Nodes (33): BaseHTTPMiddleware, _build_engine(), get_engine(), get_session_factory(), _init(), _normalise_url(), SQLAlchemy engine and session factory for Postgres persistence.  The engine is, Return the session factory bound to the shared engine.      Returns: (+25 more)

### Community 9 - "Investment Achievement Report"
Cohesion: 0.11
Nodes (44): InvestmentPlanEntry, A single row from the quarterly investment plan sheet.      Attributes:, format_achievement_reply(), _format_symbol_row(), get_quarterly_achievement_rate(), _progress_bar(), QuarterlyAchievementReport, Service for computing quarterly investment achievement rates.  Reads from the (+36 more)

### Community 10 - "Portfolio PnL Repository"
Cohesion: 0.07
Nodes (27): _fetch_pnl_cell(), fetch_pnl_tw(), fetch_pnl_us(), fetch_portfolio(), fetch_portfolio_us(), _normalize_us_symbol(), _parse_number(), Repository for reading personal portfolio data from Google Sheets CSV export. (+19 more)

### Community 11 - "Signal History Redis Repo"
Cohesion: 0.12
Nodes (27): _build_key(), _dict_to_record(), list_signals(), _parse_key_date(), Repository for persisting cost-level signal history in Redis.  Signals are wri, Persist a signal record to Redis with a 120-day TTL.      Redis errors are swa, Extract the date component from a signal history key.      Args:         key:, Return all signal records whose key-date falls within [start_date, end_date]. (+19 more)

### Community 12 - "Sheets Archive Writer"
Cohesion: 0.12
Nodes (38): append_monthly_history(), _decimal_cell(), _delete_existing_period_rows(), _find_worksheet_by_gid(), _load_service_account_info(), Google Sheets archive writer for monthly portfolio history (spec-006 B).  Appe, Project a snapshot to the column order required by the Sheet., Locate a worksheet by ``gid`` within a spreadsheet.      Args:         spread (+30 more)

### Community 13 - "Report Builder Tests"
Cohesion: 0.13
Nodes (16): build_weekly_report(), _format_signal_trajectory(), _patch_repos(), _signal(), test_build_monthly_report_happy_path(), test_build_monthly_report_saves_snapshot_for_prev_month(), test_build_weekly_report_empty_signals(), test_build_weekly_report_fetch_failure_shows_placeholder() (+8 more)

### Community 14 - "Stock Message Formatter"
Cohesion: 0.15
Nodes (6): format_rich_stock_message(), _make_stock(), Tests for the rich Telegram message formatter., US pre-market display flips line 2/3 to show live pre-market price., TestFormatRichStockMessage, TestPreMarketDisplay

### Community 15 - "Portfolio Snapshot Repo"
Cohesion: 0.11
Nodes (25): _dict_to_snapshot(), get_monthly(), get_weekly(), _load(), Repository for persisting periodic portfolio snapshots in Redis.  Snapshots ar, Persist a monthly snapshot keyed by YYYY-MM of the snapshot's timestamp., Read the weekly snapshot for *iso_date* (YYYY-MM-DD).      Args:         iso_, Read the monthly snapshot for *year_month* (YYYY-MM).      Args:         year (+17 more)

### Community 16 - "Webhook Auth Tests"
Cohesion: 0.18
Nodes (9): _callback_update(), _message_update(), _post(), _snapshot(), _summary(), TestCallbackMalformed, TestCallbackQueryFlow, TestHistoryTextCommand (+1 more)

### Community 17 - "Cost Signal Persistence"
Cohesion: 0.14
Nodes (3): _calc_cost_signal(), TestCalcCostSignalPersistIntegration, TestCalcCostSignal

### Community 18 - "Callback & Keyboard Handlers"
Cohesion: 0.21
Nodes (21): _build_inline_keyboard(), _fetch_symbol_rows(), _format_decimal(), _format_summary_text(), _format_symbol_text(), handle_callback(), handle_text_command(), _now() (+13 more)

### Community 19 - "US Stock Service Tests"
Cohesion: 0.14
Nodes (19): Tests for US stock service (cache + parallel fetch)., redis_cache.put must be called with the US_STOCK_CACHE_TTL value., test_get_us_stock_cache_hit_returns_cached(), test_get_us_stock_cache_miss_fetches_and_stores(), test_get_us_stock_cache_put_uses_us_stock_cache_ttl(), test_get_us_stocks_all_cache_hits(), test_get_us_stocks_merges_portfolio_fields(), test_get_us_stocks_parallel_fetch() (+11 more)

### Community 20 - "US Stock Repo Tests"
Cohesion: 0.26
Nodes (17): _make_hist(), _make_premarket_hist(), _make_ticker_mock(), test_empty_history_raises_stock_not_found(), test_fetch_premarket_price_returns_none_on_empty_hist(), test_fetch_premarket_price_returns_none_on_exception(), test_fetch_premarket_price_returns_none_outside_window(), test_fetch_premarket_price_returns_none_when_no_premarket_rows() (+9 more)

### Community 21 - "Webhook Integration Tests"
Cohesion: 0.32
Nodes (14): _make_update(), _post(), Integration tests for POST /api/v1/webhook/telegram., test_correct_secret_passes(), test_help_command_replies_with_menu(), test_missing_secret_returns_403(), test_non_text_message_ignored(), test_q_command_dispatched() (+6 more)

### Community 22 - "Reports Router Tests"
Cohesion: 0.14
Nodes (7): Integration tests for the reports router (/api/v1/reports/*).  These tests cov, Verify the dedicated /api/v1/reports rate-limit bucket is wired up., TestMonthlyPreview, TestMonthlySend, TestReportsRateLimit, TestWeeklyPreview, TestWeeklySend

### Community 23 - "Alembic DB Migration"
Cohesion: 0.5
Nodes (1): initial snapshot tables  Revision ID: eeb0be489f4b Revises: Create Date: 202

### Community 24 - "Telegram Update Models"
Cohesion: 0.5
Nodes (4): TelegramChat (Pydantic), TelegramFrom (Pydantic), TelegramMessage (Pydantic), TelegramUpdate (Pydantic)

### Community 25 - "Backfill CLI Scripts"
Cohesion: 0.67
Nodes (3): scripts/backfill_history.py (CLI Management), scripts/backfill_history.py (CLI Backfill from Earliest Transaction Month), --repair-deltas CLI Flag (Recalculate pnl_*_delta Without Re-fetching yfinance)

### Community 26 - "Webhook Security Design"
Cohesion: 0.67
Nodes (3): Decision: X-Telegram-Bot-Api-Secret-Token Header Verification, FR-003: Secret Token Validation (X-Telegram-Bot-Api-Secret-Token), Rationale: IP Whitelist Rejected (High Maintenance, Telegram IPs Change)

### Community 27 - "Webhook Startup Decision"
Cohesion: 1.0
Nodes (2): Decision: setWebhook Called Once Manually (Not at Startup), Rationale: setWebhook Is Not Idempotent-Safe at Every Restart

### Community 28 - "Module Initializer"
Cohesion: 1.0
Nodes (0): 

### Community 29 - "Technical Indicators"
Cohesion: 1.0
Nodes (1): services/indicators.py

### Community 30 - "Transactions Repository"
Cohesion: 1.0
Nodes (1): repositories/transactions_repo.py

### Community 31 - "Scheduler Architecture"
Cohesion: 1.0
Nodes (1): APScheduler Decision

### Community 32 - "Response Envelope"
Cohesion: 1.0
Nodes (1): Community: Response Envelope & Schemas

### Community 33 - "Redis Cache Layer"
Cohesion: 1.0
Nodes (1): Community: Redis Cache Layer

### Community 34 - "Bot Command Spec"
Cohesion: 1.0
Nodes (1): Community: Bot Commands & Webhook Spec

### Community 35 - "Railway CI/CD"
Cohesion: 1.0
Nodes (1): Community: Railway CI/CD Pipeline

### Community 36 - "Webhook Secret Config"
Cohesion: 1.0
Nodes (1): Env: TELEGRAM_WEBHOOK_SECRET

### Community 37 - "Sheets GID Config"
Cohesion: 1.0
Nodes (1): Env: GOOGLE_SHEETS_INVESTMENT_PLAN_GID

### Community 38 - "Bot Menu Registration"
Cohesion: 1.0
Nodes (1): Decision: setMyCommands at App Startup (Idempotent)

### Community 39 - "Progress Bar Format"
Cohesion: 1.0
Nodes (1): Progress Bar Format (▓/░ 10 Cells)

### Community 40 - "Unauthorized User Filter"
Cohesion: 1.0
Nodes (1): FR-002: Silently Ignore Unauthorized Telegram User IDs

### Community 41 - "TW Signal Thresholds"
Cohesion: 1.0
Nodes (1): _TW_SIGNAL_THRESHOLDS (20%/25%/30% Drop)

### Community 42 - "US Signal Thresholds"
Cohesion: 1.0
Nodes (1): _US_SIGNAL_THRESHOLDS (20%/30%/40% Drop)

### Community 43 - "Investment Target Config"
Cohesion: 1.0
Nodes (1): Env: REGULAR_INVESTMENT_TARGET_TWD (Default 100000)

### Community 44 - "DB Engine File"
Cohesion: 1.0
Nodes (1): db/engine.py (SQLAlchemy Engine + Session Factory)

### Community 45 - "Database URL Config"
Cohesion: 1.0
Nodes (1): Env: DATABASE_URL (Postgres Connection)

### Community 46 - "Sheets Auth Config"
Cohesion: 1.0
Nodes (1): Env: GOOGLE_SERVICE_ACCOUNT_JSON/B64 (Sheets Write Auth)

### Community 47 - "Dev Setup Guide"
Cohesion: 1.0
Nodes (1): Quickstart: fastApiStock Development Setup

## Knowledge Gaps
- **180 isolated node(s):** `initial snapshot tables  Revision ID: eeb0be489f4b Revises: Create Date: 202`, `Parse an optional integer env var.      Args:         env_name: Environment v`, `Parse TW_STOCKS env var into a list of Taiwan stock codes.      Returns:`, `Parse US_STOCKS env var into a list of uppercased US stock tickers.      Retur`, `Build the Redis connection URL for the rate-limiter storage backend.      Retu` (+175 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Webhook Startup Decision`** (2 nodes): `Decision: setWebhook Called Once Manually (Not at Startup)`, `Rationale: setWebhook Is Not Idempotent-Safe at Every Restart`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Initializer`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Technical Indicators`** (1 nodes): `services/indicators.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Transactions Repository`** (1 nodes): `repositories/transactions_repo.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Scheduler Architecture`** (1 nodes): `APScheduler Decision`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Response Envelope`** (1 nodes): `Community: Response Envelope & Schemas`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Redis Cache Layer`** (1 nodes): `Community: Redis Cache Layer`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Bot Command Spec`** (1 nodes): `Community: Bot Commands & Webhook Spec`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Railway CI/CD`** (1 nodes): `Community: Railway CI/CD Pipeline`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Webhook Secret Config`** (1 nodes): `Env: TELEGRAM_WEBHOOK_SECRET`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Sheets GID Config`** (1 nodes): `Env: GOOGLE_SHEETS_INVESTMENT_PLAN_GID`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Bot Menu Registration`** (1 nodes): `Decision: setMyCommands at App Startup (Idempotent)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Progress Bar Format`** (1 nodes): `Progress Bar Format (▓/░ 10 Cells)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Unauthorized User Filter`** (1 nodes): `FR-002: Silently Ignore Unauthorized Telegram User IDs`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TW Signal Thresholds`** (1 nodes): `_TW_SIGNAL_THRESHOLDS (20%/25%/30% Drop)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `US Signal Thresholds`** (1 nodes): `_US_SIGNAL_THRESHOLDS (20%/30%/40% Drop)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Investment Target Config`** (1 nodes): `Env: REGULAR_INVESTMENT_TARGET_TWD (Default 100000)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `DB Engine File`** (1 nodes): `db/engine.py (SQLAlchemy Engine + Session Factory)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Database URL Config`** (1 nodes): `Env: DATABASE_URL (Postgres Connection)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Sheets Auth Config`** (1 nodes): `Env: GOOGLE_SERVICE_ACCOUNT_JSON/B64 (Sheets Write Auth)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Dev Setup Guide`** (1 nodes): `Quickstart: fastApiStock Development Setup`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SymbolSnapshot` connect `History Command & Inline Keyboards` to `Test Fixtures & Fakes`, `Report Pipeline Tests`, `History Backfill CLI`, `Sheets Archive Writer`, `Webhook Auth Tests`?**
  _High betweenness centrality (0.130) - this node is a cross-community bridge._
- **Why does `SignalRecord` connect `History Command & Inline Keyboards` to `Schema & Service Layer`, `Investment Plan Repository`, `Report Pipeline Tests`, `Database Engine & Session`, `Signal History Redis Repo`, `Report Builder Tests`, `Portfolio Snapshot Repo`, `Cost Signal Persistence`?**
  _High betweenness centrality (0.123) - this node is a cross-community bridge._
- **Why does `ReportSummary` connect `History Command & Inline Keyboards` to `Webhook Auth Tests`, `Test Fixtures & Fakes`, `Report Pipeline Tests`, `History Backfill CLI`?**
  _High betweenness centrality (0.119) - this node is a cross-community bridge._
- **Are the 151 inferred relationships involving `SymbolSnapshot` (e.g. with `PortfolioReportSummary` and `PortfolioSymbolSnapshot`) actually correct?**
  _`SymbolSnapshot` has 151 INFERRED edges - model-reasoned connections that need verification._
- **Are the 143 inferred relationships involving `ReportSummary` (e.g. with `PortfolioReportSummary` and `PortfolioSymbolSnapshot`) actually correct?**
  _`ReportSummary` has 143 INFERRED edges - model-reasoned connections that need verification._
- **Are the 127 inferred relationships involving `PortfolioSnapshot` (e.g. with `_SymbolPortfolio` and `Standalone CLI script: backfill monthly portfolio history into Postgres + Sheets`) actually correct?**
  _`PortfolioSnapshot` has 127 INFERRED edges - model-reasoned connections that need verification._
- **Are the 116 inferred relationships involving `SignalRecord` (e.g. with `_ReportWindow` and `_FetchResults`) actually correct?**
  _`SignalRecord` has 116 INFERRED edges - model-reasoned connections that need verification._