# Graph Report - D:\claude\fastApiStock  (2026-05-20)

## Corpus Check
- 91 files · ~212,888 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1879 nodes · 4220 edges · 91 communities detected
- Extraction: 58% EXTRACTED · 42% INFERRED · 0% AMBIGUOUS · INFERRED: 1774 edges (avg confidence: 0.64)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 90|Community 90]]

## God Nodes (most connected - your core abstractions)
1. `SymbolSnapshot` - 154 edges
2. `ReportSummary` - 146 edges
3. `PortfolioSnapshot` - 143 edges
4. `SignalRecord` - 129 edges
5. `get()` - 103 edges
6. `StructuredJsonFormatter` - 88 edges
7. `RichStockData` - 83 edges
8. `PortfolioEntry` - 71 edges
9. `StockData` - 56 edges
10. `format_rich_stock_message()` - 41 edges

## Surprising Connections (you probably didn't know these)
- `Unit tests for the StructuredJsonFormatter (Spec 007, T004).` --uses--> `StructuredJsonFormatter`  [INFERRED]
  D:\claude\fastApiStock\tests\test_json_formatter.py → D:\claude\fastApiStock\src\fastapistock\core\json_formatter.py
- `Emit one log record and return the parsed JSON dict.` --uses--> `StructuredJsonFormatter`  [INFERRED]
  D:\claude\fastApiStock\tests\test_json_formatter.py → D:\claude\fastApiStock\src\fastapistock\core\json_formatter.py
- `test_portfolio_entry_immutable()` --calls--> `PortfolioEntry`  [INFERRED]
  tests\test_portfolio_repo.py → src\fastapistock\repositories\portfolio_repo.py
- `Service layer for portfolio PnL command.` --uses--> `PortfolioSnapshot`  [INFERRED]
  src\fastapistock\services\portfolio_service.py → D:\claude\fastApiStock\src\fastapistock\repositories\portfolio_snapshot_repo.py
- `Build the Telegram reply string for the /pnl command.      Handles three cases` --uses--> `PortfolioSnapshot`  [INFERRED]
  D:\claude\fastApiStock\src\fastapistock\services\portfolio_service.py → D:\claude\fastApiStock\src\fastapistock\repositories\portfolio_snapshot_repo.py

## Hyperedges (group relationships)
- **Feature Progression 003→004→005→006** — spec003_feature, spec004_cost_level_signal, spec005_signal_history, spec006_report_history_postgres [EXTRACTED 0.95]
- **Webhook Command Dispatch Pipeline (/q /us /tw /pnl /history /help)** — arch_webhook_router, spec003_command_q, spec003_command_us, spec003_command_tw, main_pnl_command, spec003_command_help, spec006_history_command_inline [EXTRACTED 0.95]
- **Redis Caching Pattern (investment_plan, pnl, signal, options)** — spec003_investment_plan_cache_key, main_pnl_cache_key, spec005_signal_redis_key, spec006_history_options_api, arch_redis_cache [INFERRED 0.85]
- **Report Pipeline: Telegram→Postgres→Sheet (run_report_pipeline)** — spec006_run_report_pipeline, arch_telegram_service, spec006_report_history_repo, spec006_sheet_writer, spec006_run_report_result [EXTRACTED 0.95]
- **RichStockData Consumers (stock_service, us_stock_service, telegram_service)** — arch_rich_stock_data, arch_stock_service, arch_us_stock_service, arch_telegram_service, spec004_week52_high_field, spec004_ma50_field [INFERRED 0.85]
- **Postgres Persistence Group (report_history_repo, db/engine, alembic)** — spec006_report_history_repo, spec006_db_engine, spec006_db_models, spec006_alembic, arch_postgres [EXTRACTED 0.95]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.02
Nodes (241): Recalculate pnl_tw_delta and pnl_us_delta from existing DB summary rows., Shared response envelope schema used by all API endpoints., Standard API response wrapper.      All endpoints return this envelope so cons, ResponseEnvelope, health_check(), Return a liveness signal.      Returns:         ResponseEnvelope with data={', Telegram ``/history`` command + inline-keyboard interaction (spec-006 D).  The, Resolve ``(symbol, market)`` and load the per-symbol monthly series.      When (+233 more)

### Community 1 - "Community 1"
Cohesion: 0.02
Nodes (94): get(), _get_client(), invalidate(), put(), Redis-backed cache for stock data with native TTL support.  The module holds a, Return the shared Redis client, creating it on first call.      Returns:, Return the cached value for *key*, or ``None`` on miss or error.      Args:, Store *value* under *key* with an expiry of *ttl* seconds.      Args: (+86 more)

### Community 2 - "Community 2"
Cohesion: 0.02
Nodes (96): BaseHTTPMiddleware, _generic_exception_handler(), Custom exception handlers that return the standard ResponseEnvelope., Return a 404 envelope for unknown stock symbols.      Args:         _request:, Override FastAPI's default 422 handler to use the ResponseEnvelope.      Args:, Catch-all 500 handler that returns the ResponseEnvelope.      Args:         _, Register all exception handlers on the FastAPI application.      Args:, register_exception_handlers() (+88 more)

### Community 3 - "Community 3"
Cohesion: 0.02
Nodes (128): Google Sheets (External), services/history_handler.py, repositories/investment_plan_repo.py, services/investment_plan_service.py, middleware/logging.py LoggingMiddleware, main.py FastAPI App + Lifespan, PortfolioEntry (repositories/portfolio_repo.py), repositories/portfolio_repo.py (+120 more)

### Community 4 - "Community 4"
Cohesion: 0.04
Nodes (75): BaseModel, IndicatorResult, Computed technical indicators from a stock's price history.      Attributes:, Pydantic schemas for the stock domain., Full technical-analysis snapshot used by the scheduler and rich API endpoints., Real-time stock snapshot returned by GET /api/v1/stock/{id}.      Attributes:, RichStockData, StockData (+67 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (93): _repair_deltas(), db_session(), _fake_redis(), Shared pytest fixtures for the fastapistock test suite., Render ``BigInteger`` as ``INTEGER`` for SQLite so rowid autoincrement works., Replace all Redis clients with in-memory fakeredis instances.      Patches the, Yield a SQLite in-memory session isolated from production singletons.      The, _sqlite_bigint_as_integer() (+85 more)

### Community 6 - "Community 6"
Cohesion: 0.04
Nodes (68): _fetch_pnl_cell(), fetch_pnl_tw(), fetch_pnl_us(), fetch_portfolio(), fetch_portfolio_us(), _normalize_us_symbol(), _parse_number(), Repository for reading personal portfolio data from Google Sheets CSV export. (+60 more)

### Community 7 - "Community 7"
Cohesion: 0.04
Nodes (56): load_config(), _optional_int(), RateLimitConfig, Rate limit configuration loaded from environment variables.  Each route group, Build the Redis connection URL for the rate-limiter storage backend.      Retu, Immutable rate limit parameters for one route group.      Attributes:, Parse an optional integer env var.      Args:         env_name: Environment v, Build a ``RateLimitConfig`` from environment variables.      Args:         pr (+48 more)

### Community 8 - "Community 8"
Cohesion: 0.06
Nodes (72): _build_inline_keyboard(), _fetch_symbol_rows(), _format_decimal(), _format_summary_text(), _format_symbol_text(), handle_callback(), handle_text_command(), _now() (+64 more)

### Community 9 - "Community 9"
Cohesion: 0.06
Nodes (67): _dict_to_entry(), _entry_to_dict(), fetch_investment_plan(), _fetch_live(), InvestmentPlanEntry, _parse_date(), _parse_number(), Repository for reading quarterly investment plan data from Google Sheets CSV exp (+59 more)

### Community 10 - "Community 10"
Cohesion: 0.06
Nodes (49): test_parse_date_dash_format(), test_parse_date_empty_returns_none(), test_parse_date_invalid_returns_none(), test_parse_date_slash_format(), _make_csv(), _mock_response(), TestTransactionsEdgeCases, _make_csv() (+41 more)

### Community 11 - "Community 11"
Cohesion: 0.07
Nodes (58): _backfill_month(), _build_parser(), _build_tw_name_to_code(), _build_tw_snapshots(), _build_us_snapshots(), _fetch_close_price(), _fetch_usd_twd_rate(), main() (+50 more)

### Community 12 - "Community 12"
Cohesion: 0.09
Nodes (34): _get_client(), RateLimiter, Redis sliding-window rate limiter implementation.  Uses two Redis keys per (ip, Return the shared Redis client, creating it on first call.      Returns:, Sliding-window IP rate limiter backed by Redis sorted sets.      Each instance, Initialise a limiter for one route group.          Args:             config:, Check and record a request for *ip*.          Steps:           1. Return True, _build_key() (+26 more)

### Community 13 - "Community 13"
Cohesion: 0.09
Nodes (19): Router for Telegram notification endpoints.  All routes live under /api/v1/tgM, Fetch stock data and push a formatted message to a Telegram user.      Non-num, send_telegram_stock_info(), format_rich_stock_message(), send_rich_stock_message(), _make_stock(), Tests for the rich Telegram message formatter., US pre-market display flips line 2/3 to show live pre-market price. (+11 more)

### Community 14 - "Community 14"
Cohesion: 0.09
Nodes (22): _bollinger(), calculate(), _macd(), Technical indicator calculations for stock data.  All functions are pure: they, Compute MACD line, signal line, and histogram.      Args:         series: Clo, Compute Bollinger Bands (upper, middle, lower).      Args:         series: Cl, Compute all technical indicators from a yfinance history DataFrame.      Args:, Produce a technical analysis verdict from indicator values.      Scoring range (+14 more)

### Community 15 - "Community 15"
Cohesion: 0.09
Nodes (33): _dict_to_snapshot(), get_daily(), get_monthly(), get_weekly(), _load(), _normalize_market(), Repository for persisting periodic portfolio snapshots in Redis.  Snapshots ar, Persist a daily market-close snapshot.      Args:         market: Market code (+25 more)

### Community 16 - "Community 16"
Cohesion: 0.12
Nodes (38): append_monthly_history(), _decimal_cell(), _delete_existing_period_rows(), _find_worksheet_by_gid(), _load_service_account_info(), Google Sheets archive writer for monthly portfolio history (spec-006 B).  Appe, Project a snapshot to the column order required by the Sheet., Locate a worksheet by ``gid`` within a spreadsheet.      Args:         spread (+30 more)

### Community 17 - "Community 17"
Cohesion: 0.13
Nodes (16): build_weekly_report(), _format_signal_trajectory(), _patch_repos(), _signal(), test_build_monthly_report_happy_path(), test_build_monthly_report_saves_snapshot_for_prev_month(), test_build_weekly_report_empty_signals(), test_build_weekly_report_fetch_failure_shows_placeholder() (+8 more)

### Community 18 - "Community 18"
Cohesion: 0.1
Nodes (14): build_scheduler(), Create and configure an APScheduler AsyncIOScheduler.      Adds a single inter, The weekly cron job must invoke run_report_pipeline with the correct args., The monthly cron job must invoke run_report_pipeline with cron args., Use functools.partial so tests can inspect args without invocation., Verify the monthly_report job uses the first-Sunday CronTrigger (008)., day_of_week field must be 'sun' (every Sunday)., day field must restrict to 1-7 so only the first Sunday fires. (+6 more)

### Community 19 - "Community 19"
Cohesion: 0.08
Nodes (15): admin_token(), _make_result(), Tests for ``POST /api/v1/reports/history/trigger`` (spec-006 Phase 5).  The en, Pydantic-driven 422 cases., Successful 200 paths verifying envelope + pipeline arguments., 503 must take precedence over body validation to avoid leaking schema., Sanity check that asdict() is what serialises the result., Build a deterministic ``RunReportResult`` for assertion. (+7 more)

### Community 20 - "Community 20"
Cohesion: 0.18
Nodes (9): _callback_update(), _message_update(), _post(), _snapshot(), _summary(), TestCallbackMalformed, TestCallbackQueryFlow, TestHistoryTextCommand (+1 more)

### Community 21 - "Community 21"
Cohesion: 0.11
Nodes (22): Tests for US stock service (cache + parallel fetch)., redis_cache.put must be called with the US_STOCK_CACHE_TTL value., test_get_us_stock_cache_hit_returns_cached(), test_get_us_stock_cache_miss_fetches_and_stores(), test_get_us_stock_cache_put_uses_us_stock_cache_ttl(), test_get_us_stocks_all_cache_hits(), test_get_us_stocks_merges_portfolio_fields(), test_get_us_stocks_parallel_fetch() (+14 more)

### Community 22 - "Community 22"
Cohesion: 0.14
Nodes (3): _calc_cost_signal(), TestCalcCostSignalPersistIntegration, TestCalcCostSignal

### Community 23 - "Community 23"
Cohesion: 0.17
Nodes (14): _client_ip(), _level(), _mask_sensitive(), Structured request/response/performance logging middleware.  Emits three log l, Map HTTP status code to Python logging level.      Args:         status: HTTP, Log request, invoke handler, then log response and timing.          Args:, Extract the real client IP, preferring X-Forwarded-For.      Args:         re, Replace values of sensitive keys with ``***``.      Args:         text: Seria (+6 more)

### Community 24 - "Community 24"
Cohesion: 0.32
Nodes (14): _make_update(), _post(), Integration tests for POST /api/v1/webhook/telegram., test_correct_secret_passes(), test_help_command_replies_with_menu(), test_missing_secret_returns_403(), test_non_text_message_ignored(), test_q_command_dispatched() (+6 more)

### Community 25 - "Community 25"
Cohesion: 0.31
Nodes (5): _capture_json(), _make_formatter(), Unit tests for the StructuredJsonFormatter (Spec 007, T004)., Emit one log record and return the parsed JSON dict., TestStructuredJsonFormatter

### Community 26 - "Community 26"
Cohesion: 0.17
Nodes (5): Unit tests for spec 009 — _BOT_COMMANDS completeness., AC T1: 第 2 個 entry（index 1）必須為 pnl。, AC T1: 第 5 個 entry（index 4）必須為 history。, test_history_is_at_index_4(), test_pnl_is_at_index_1()

### Community 27 - "Community 27"
Cohesion: 0.5
Nodes (1): initial snapshot tables  Revision ID: eeb0be489f4b Revises: Create Date: 202

### Community 28 - "Community 28"
Cohesion: 0.5
Nodes (3): api_index(), Root index router — lists all available API endpoints., Return a summary of every registered API route.      Args:         request: F

### Community 29 - "Community 29"
Cohesion: 0.5
Nodes (4): TelegramChat (Pydantic), TelegramFrom (Pydantic), TelegramMessage (Pydantic), TelegramUpdate (Pydantic)

### Community 30 - "Community 30"
Cohesion: 0.67
Nodes (3): scripts/backfill_history.py (CLI Management), scripts/backfill_history.py (CLI Backfill from Earliest Transaction Month), --repair-deltas CLI Flag (Recalculate pnl_*_delta Without Re-fetching yfinance)

### Community 31 - "Community 31"
Cohesion: 0.67
Nodes (3): Decision: X-Telegram-Bot-Api-Secret-Token Header Verification, FR-003: Secret Token Validation (X-Telegram-Bot-Api-Secret-Token), Rationale: IP Whitelist Rejected (High Maintenance, Telegram IPs Change)

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (2): Decision: setWebhook Called Once Manually (Not at Startup), Rationale: setWebhook Is Not Idempotent-Safe at Every Restart

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (0): 

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (0): 

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (0): 

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (0): 

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (0): 

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (0): 

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (0): 

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (0): 

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (0): 

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (1): Parse TW_STOCKS env var into a list of Taiwan stock codes.      Returns:

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): Parse US_STOCKS env var into a list of uppercased US stock tickers.      Retur

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Build the Redis connection URL for the rate-limiter storage backend.      Retu

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Register the bot command menu with Telegram via setMyCommands.      This is an

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): Probe the configured Postgres database at application startup.      Logs a str

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): Middleware that applies per-route sliding-window rate limiting.      Routes in

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): Intercept each request and enforce the rate limit.          Args:

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): Build and configure the FastAPI application.      Returns:         A fully co

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): Return True when *now* falls in the Taiwan stock push window.      Window: Mon

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Return True when *now* falls in the US stock push window.      Window: Monday–

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Fetch configured Taiwan stocks and send a rich Telegram message.      Reads TW

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): Fetch configured US stocks and send a rich Telegram message.      Reads US_STO

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (1): Check time windows and trigger appropriate market pushes.      Called by APSch

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (1): Create and configure an APScheduler AsyncIOScheduler.      Adds a single inter

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): Immutable snapshot of the portfolio's total unrealized PnL.      Attributes:

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (1): Serialise a PortfolioSnapshot to a JSON-safe dict.

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (1): Deserialise a cached dict into a PortfolioSnapshot, None on malformed input.

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (1): Persist a snapshot under *key* with the standard TTL.

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (1): Read a snapshot at *key*; return None on miss, malformed data, or error.

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (1): Persist a weekly snapshot keyed by the snapshot date (YYYY-MM-DD).      Args:

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (1): Persist a monthly snapshot keyed by YYYY-MM of the snapshot's timestamp.

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (1): Read the weekly snapshot for *iso_date* (YYYY-MM-DD).      Args:         iso_

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (1): Read the monthly snapshot for *year_month* (YYYY-MM).      Args:         year

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (1): Build the Telegram reply string for the /pnl command.      Handles three cases

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (1): Fetch TW and US PnL and return a formatted Telegram reply string.      Returns

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (1): Build a datetime in Asia/Taipei for a given weekday offset from Monday.      A

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (1): The weekly cron job must invoke run_report_pipeline with the correct args.

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (1): The monthly cron job must invoke run_report_pipeline with cron args.

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (1): Use functools.partial so tests can inspect args without invocation.

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (1): services/indicators.py

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (1): repositories/transactions_repo.py

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (1): APScheduler Decision

### Community 75 - "Community 75"
Cohesion: 1.0
Nodes (1): Community: Response Envelope & Schemas

### Community 76 - "Community 76"
Cohesion: 1.0
Nodes (1): Community: Redis Cache Layer

### Community 77 - "Community 77"
Cohesion: 1.0
Nodes (1): Community: Bot Commands & Webhook Spec

### Community 78 - "Community 78"
Cohesion: 1.0
Nodes (1): Community: Railway CI/CD Pipeline

### Community 79 - "Community 79"
Cohesion: 1.0
Nodes (1): Env: TELEGRAM_WEBHOOK_SECRET

### Community 80 - "Community 80"
Cohesion: 1.0
Nodes (1): Env: GOOGLE_SHEETS_INVESTMENT_PLAN_GID

### Community 81 - "Community 81"
Cohesion: 1.0
Nodes (1): Decision: setMyCommands at App Startup (Idempotent)

### Community 82 - "Community 82"
Cohesion: 1.0
Nodes (1): Progress Bar Format (▓/░ 10 Cells)

### Community 83 - "Community 83"
Cohesion: 1.0
Nodes (1): FR-002: Silently Ignore Unauthorized Telegram User IDs

### Community 84 - "Community 84"
Cohesion: 1.0
Nodes (1): _TW_SIGNAL_THRESHOLDS (20%/25%/30% Drop)

### Community 85 - "Community 85"
Cohesion: 1.0
Nodes (1): _US_SIGNAL_THRESHOLDS (20%/30%/40% Drop)

### Community 86 - "Community 86"
Cohesion: 1.0
Nodes (1): Env: REGULAR_INVESTMENT_TARGET_TWD (Default 100000)

### Community 87 - "Community 87"
Cohesion: 1.0
Nodes (1): db/engine.py (SQLAlchemy Engine + Session Factory)

### Community 88 - "Community 88"
Cohesion: 1.0
Nodes (1): Env: DATABASE_URL (Postgres Connection)

### Community 89 - "Community 89"
Cohesion: 1.0
Nodes (1): Env: GOOGLE_SERVICE_ACCOUNT_JSON/B64 (Sheets Write Auth)

### Community 90 - "Community 90"
Cohesion: 1.0
Nodes (1): Quickstart: fastApiStock Development Setup

## Knowledge Gaps
- **299 isolated node(s):** `initial snapshot tables  Revision ID: eeb0be489f4b Revises: Create Date: 202`, `Parse an optional integer env var.      Args:         env_name: Environment v`, `Parse TW_STOCKS env var into a list of Taiwan stock codes.      Returns:`, `Parse US_STOCKS env var into a list of uppercased US stock tickers.      Retur`, `Build the Redis connection URL for the rate-limiter storage backend.      Retu` (+294 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 32`** (2 nodes): `Decision: setWebhook Called Once Manually (Not at Startup)`, `Rationale: setWebhook Is Not Idempotent-Safe at Every Restart`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `Parse TW_STOCKS env var into a list of Taiwan stock codes.      Returns:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `Parse US_STOCKS env var into a list of uppercased US stock tickers.      Retur`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `Build the Redis connection URL for the rate-limiter storage backend.      Retu`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `Register the bot command menu with Telegram via setMyCommands.      This is an`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `Probe the configured Postgres database at application startup.      Logs a str`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `Middleware that applies per-route sliding-window rate limiting.      Routes in`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `Intercept each request and enforce the rate limit.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `Build and configure the FastAPI application.      Returns:         A fully co`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `Return True when *now* falls in the Taiwan stock push window.      Window: Mon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `Return True when *now* falls in the US stock push window.      Window: Monday–`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `Fetch configured Taiwan stocks and send a rich Telegram message.      Reads TW`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `Fetch configured US stocks and send a rich Telegram message.      Reads US_STO`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `Check time windows and trigger appropriate market pushes.      Called by APSch`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `Create and configure an APScheduler AsyncIOScheduler.      Adds a single inter`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `Immutable snapshot of the portfolio's total unrealized PnL.      Attributes:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `Serialise a PortfolioSnapshot to a JSON-safe dict.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `Deserialise a cached dict into a PortfolioSnapshot, None on malformed input.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `Persist a snapshot under *key* with the standard TTL.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `Read a snapshot at *key*; return None on miss, malformed data, or error.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (1 nodes): `Persist a weekly snapshot keyed by the snapshot date (YYYY-MM-DD).      Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (1 nodes): `Persist a monthly snapshot keyed by YYYY-MM of the snapshot's timestamp.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `Read the weekly snapshot for *iso_date* (YYYY-MM-DD).      Args:         iso_`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (1 nodes): `Read the monthly snapshot for *year_month* (YYYY-MM).      Args:         year`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (1 nodes): `Build the Telegram reply string for the /pnl command.      Handles three cases`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (1 nodes): `Fetch TW and US PnL and return a formatted Telegram reply string.      Returns`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (1 nodes): `Build a datetime in Asia/Taipei for a given weekday offset from Monday.      A`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (1 nodes): `The weekly cron job must invoke run_report_pipeline with the correct args.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (1 nodes): `The monthly cron job must invoke run_report_pipeline with cron args.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (1 nodes): `Use functools.partial so tests can inspect args without invocation.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (1 nodes): `services/indicators.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (1 nodes): `repositories/transactions_repo.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (1 nodes): `APScheduler Decision`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (1 nodes): `Community: Response Envelope & Schemas`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (1 nodes): `Community: Redis Cache Layer`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 77`** (1 nodes): `Community: Bot Commands & Webhook Spec`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 78`** (1 nodes): `Community: Railway CI/CD Pipeline`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 79`** (1 nodes): `Env: TELEGRAM_WEBHOOK_SECRET`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 80`** (1 nodes): `Env: GOOGLE_SHEETS_INVESTMENT_PLAN_GID`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 81`** (1 nodes): `Decision: setMyCommands at App Startup (Idempotent)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 82`** (1 nodes): `Progress Bar Format (▓/░ 10 Cells)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 83`** (1 nodes): `FR-002: Silently Ignore Unauthorized Telegram User IDs`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 84`** (1 nodes): `_TW_SIGNAL_THRESHOLDS (20%/25%/30% Drop)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 85`** (1 nodes): `_US_SIGNAL_THRESHOLDS (20%/30%/40% Drop)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 86`** (1 nodes): `Env: REGULAR_INVESTMENT_TARGET_TWD (Default 100000)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 87`** (1 nodes): `db/engine.py (SQLAlchemy Engine + Session Factory)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 88`** (1 nodes): `Env: DATABASE_URL (Postgres Connection)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 89`** (1 nodes): `Env: GOOGLE_SERVICE_ACCOUNT_JSON/B64 (Sheets Write Auth)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 90`** (1 nodes): `Quickstart: fastApiStock Development Setup`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get()` connect `Community 1` to `Community 0`, `Community 2`, `Community 4`, `Community 5`, `Community 6`, `Community 8`, `Community 9`, `Community 10`, `Community 11`, `Community 12`, `Community 15`, `Community 17`, `Community 21`, `Community 23`?**
  _High betweenness centrality (0.268) - this node is a cross-community bridge._
- **Why does `SignalRecord` connect `Community 0` to `Community 4`, `Community 10`, `Community 12`, `Community 15`, `Community 17`, `Community 18`, `Community 22`?**
  _High betweenness centrality (0.121) - this node is a cross-community bridge._
- **Why does `SymbolSnapshot` connect `Community 0` to `Community 1`, `Community 5`, `Community 11`, `Community 16`, `Community 20`?**
  _High betweenness centrality (0.109) - this node is a cross-community bridge._
- **Are the 151 inferred relationships involving `SymbolSnapshot` (e.g. with `_build_tw_snapshots()` and `_build_us_snapshots()`) actually correct?**
  _`SymbolSnapshot` has 151 INFERRED edges - model-reasoned connections that need verification._
- **Are the 143 inferred relationships involving `ReportSummary` (e.g. with `_backfill_month()` and `_repair_deltas()`) actually correct?**
  _`ReportSummary` has 143 INFERRED edges - model-reasoned connections that need verification._
- **Are the 140 inferred relationships involving `PortfolioSnapshot` (e.g. with `Service layer for portfolio PnL command.` and `Build the Telegram reply string for the /pnl command.      Handles three cases`) actually correct?**
  _`PortfolioSnapshot` has 140 INFERRED edges - model-reasoned connections that need verification._
- **Are the 126 inferred relationships involving `SignalRecord` (e.g. with `Telegram notification service.  Sends formatted stock information to a Telegra` and `Escape all MarkdownV2 special characters in text.      Args:         text: Ra`) actually correct?**
  _`SignalRecord` has 126 INFERRED edges - model-reasoned connections that need verification._