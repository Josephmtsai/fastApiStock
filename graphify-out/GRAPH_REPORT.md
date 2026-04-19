# Graph Report - .  (2026-04-19)

## Corpus Check
- Corpus is ~40,740 words - fits in a single context window. You may not need a graph.

## Summary
- 786 nodes · 1552 edges · 30 communities detected
- Extraction: 65% EXTRACTED · 35% INFERRED · 0% AMBIGUOUS · INFERRED: 539 edges (avg confidence: 0.69)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Response Envelope & Schemas|Response Envelope & Schemas]]
- [[_COMMUNITY_Redis Cache Layer|Redis Cache Layer]]
- [[_COMMUNITY_Project Standards & Specs|Project Standards & Specs]]
- [[_COMMUNITY_Telegram Formatter & Rich Stock|Telegram Formatter & Rich Stock]]
- [[_COMMUNITY_Scheduler & Exception Handlers|Scheduler & Exception Handlers]]
- [[_COMMUNITY_Portfolio Service & US Stocks|Portfolio Service & US Stocks]]
- [[_COMMUNITY_Technical Indicators Engine|Technical Indicators Engine]]
- [[_COMMUNITY_Investment Plan Achievement|Investment Plan Achievement]]
- [[_COMMUNITY_Bot Commands & Webhook Spec|Bot Commands & Webhook Spec]]
- [[_COMMUNITY_Stock Feature Contracts & Deploy|Stock Feature Contracts & Deploy]]
- [[_COMMUNITY_Portfolio Repository (TWUS)|Portfolio Repository (TW/US)]]
- [[_COMMUNITY_PnL Fetch & Cache|PnL Fetch & Cache]]
- [[_COMMUNITY_API Contracts & Engineering Principles|API Contracts & Engineering Principles]]
- [[_COMMUNITY_Logging Middleware|Logging Middleware]]
- [[_COMMUNITY_Investment Plan Repository|Investment Plan Repository]]
- [[_COMMUNITY_Rate Limit Config|Rate Limit Config]]
- [[_COMMUNITY_Webhook Integration Tests|Webhook Integration Tests]]
- [[_COMMUNITY_US Stock Repo Tests|US Stock Repo Tests]]
- [[_COMMUNITY_Railway CICD Pipeline|Railway CI/CD Pipeline]]
- [[_COMMUNITY_Test Fixtures (fakeredis)|Test Fixtures (fakeredis)]]
- [[_COMMUNITY_Package Init|Package Init]]
- [[_COMMUNITY_Package Init|Package Init]]
- [[_COMMUNITY_Package Init|Package Init]]
- [[_COMMUNITY_Package Init|Package Init]]
- [[_COMMUNITY_Package Init|Package Init]]
- [[_COMMUNITY_Package Init|Package Init]]
- [[_COMMUNITY_Package Init|Package Init]]
- [[_COMMUNITY_Package Init|Package Init]]
- [[_COMMUNITY_Quickstart Guide|Quickstart Guide]]
- [[_COMMUNITY_Cache Behavior Docs|Cache Behavior Docs]]

## God Nodes (most connected - your core abstractions)
1. `get()` - 60 edges
2. `RichStockData` - 49 edges
3. `StockNotFoundError` - 42 edges
4. `StockData` - 36 edges
5. `ResponseEnvelope` - 33 edges
6. `format_rich_stock_message()` - 32 edges
7. `PortfolioEntry` - 31 edges
8. `_make_stock()` - 23 edges
9. `TestFormatRichStockMessage` - 23 edges
10. `_dt()` - 22 edges

## Surprising Connections (you probably didn't know these)
- `Catch-all 500 handler that returns the ResponseEnvelope.      Args:         _` --uses--> `StockNotFoundError`  [INFERRED]
  src\fastapistock\exceptions.py → src\fastapistock\repositories\twstock_repo.py
- `Tests for portfolio_repo: CSV parsing, error handling, and degradation.` --uses--> `PortfolioEntry`  [INFERRED]
  tests\test_portfolio_repo.py → src\fastapistock\repositories\portfolio_repo.py
- `First row must never become a dict entry even if it looks numeric.` --uses--> `PortfolioEntry`  [INFERRED]
  tests\test_portfolio_repo.py → src\fastapistock\repositories\portfolio_repo.py
- `test_portfolio_entry_immutable()` --calls--> `PortfolioEntry`  [INFERRED]
  tests\test_portfolio_repo.py → src\fastapistock\repositories\portfolio_repo.py
- `Tests for the upgraded TW stock Telegram push endpoint.` --uses--> `RichStockData`  [INFERRED]
  tests\test_tw_telegram_rich.py → src\fastapistock\schemas\stock.py

## Hyperedges (group relationships)
- **TW Portfolio Enrichment Pipeline** — spec001_portfolio_repo, spec001_stock_service, spec001_telegram_service [EXTRACTED 1.00]
- **Shared Redis Cache Pattern** — spec001_redis_cache_format, spec003_investment_cache, tasks002_us2_us_portfolio_cache [INFERRED 0.85]
- **Feature Progression (001→002→003)** — spec001_feature, spec002_feature, plan003_feature [INFERRED 0.90]
- **Stock Service Data Flow** — stock_service_tw_rich, stock_service_us_stock, stock_service_scheduler_push, stock_router_tg_message, stock_router_us_telegram [INFERRED 0.85]
- **/q Command Full Flow** — 003_command_q, 003_entity_InvestmentPlanEntry, 003_entity_QuarterlyAchievementReport, concept_google_sheets_csv, concept_redis_cache [INFERRED 0.88]
- **Webhook Security Stack** — 003_env_TELEGRAM_WEBHOOK_SECRET, 003_decision_webhook_secret, 003_endpoint_POST_webhook_telegram, concept_authorized_user_filter [INFERRED 0.90]
- **PnL Data Pipeline** — entity_google_sheets_csv, entity_portfolio_repo, entity_portfolio_service, entity_webhook_router [EXTRACTED 1.00]
- **Railway Deployment Pipeline** — entity_github_actions, entity_railway_deployment, task_railway_deploy_20260405, task_railway_docker_20260405 [INFERRED 0.90]
- **Redis Shared Infrastructure** — entity_redis_cache, entity_rate_limiting, entity_portfolio_cache_ttl, entity_sliding_window_ratelimit [EXTRACTED 0.90]

## Communities

### Community 0 - "Response Envelope & Schemas"
Cohesion: 0.05
Nodes (68): BaseModel, Shared response envelope schema used by all API endpoints., Standard API response wrapper.      All endpoints return this envelope so cons, ResponseEnvelope, Custom exception handlers that return the standard ResponseEnvelope., Return a 404 envelope for unknown stock symbols.      Args:         _request:, Override FastAPI's default 422 handler to use the ResponseEnvelope.      Args:, Register all exception handlers on the FastAPI application.      Args: (+60 more)

### Community 1 - "Redis Cache Layer"
Cohesion: 0.05
Nodes (37): get(), _get_client(), invalidate(), put(), Redis-backed cache for stock data with native TTL support.  The module holds a, Return the shared Redis client, creating it on first call.      Returns:, Return the cached value for *key*, or ``None`` on miss or error.      Args:, Store *value* under *key* with an expiry of *ttl* seconds.      Args: (+29 more)

### Community 2 - "Project Standards & Specs"
Cohesion: 0.04
Nodes (62): Specification Quality Checklist 001, Standardized API Response Envelope, Conventional Commits Standard, Environment Variable Secrets Policy, KISS and YAGNI Architecture Principles, Local Cache to Avoid Repeated Fetches, Python Project Standards (UV & Ruff), pytest with 80% Coverage Target (+54 more)

### Community 3 - "Telegram Formatter & Rich Stock"
Cohesion: 0.07
Nodes (30): Full technical-analysis snapshot used by the scheduler and rich API endpoints., RichStockData, _escape_md(), _format_rich_block(), format_rich_stock_message(), _format_stock_message(), Telegram notification service.  Sends formatted stock information to a Telegra, Build a single stock's MarkdownV2 block with technical indicators.      Args: (+22 more)

### Community 4 - "Scheduler & Exception Handlers"
Cohesion: 0.07
Nodes (32): Exception, _generic_exception_handler(), Catch-all 500 handler that returns the ResponseEnvelope.      Args:         _, build_scheduler(), is_tw_market_window(), is_us_market_window(), push_tw_stocks(), push_us_stocks() (+24 more)

### Community 5 - "Portfolio Service & US Stocks"
Cohesion: 0.07
Nodes (48): PortfolioEntry, Immutable portfolio position for a single stock.      Attributes:         sym, _cache_key(), _get_cached_portfolio(), get_rich_tw_stock(), get_rich_tw_stocks(), get_stock(), get_stocks() (+40 more)

### Community 6 - "Technical Indicators Engine"
Cohesion: 0.09
Nodes (24): _bollinger(), calculate(), IndicatorResult, _macd(), Technical indicator calculations for stock data.  All functions are pure: they, Compute MACD line, signal line, and histogram.      Args:         series: Clo, Compute Bollinger Bands (upper, middle, lower).      Args:         series: Cl, Computed technical indicators from a stock's price history.      Attributes: (+16 more)

### Community 7 - "Investment Plan Achievement"
Cohesion: 0.12
Nodes (42): InvestmentPlanEntry, A single row from the quarterly investment plan sheet.      Attributes:, format_achievement_reply(), _format_symbol_row(), get_quarterly_achievement_rate(), _progress_bar(), QuarterlyAchievementReport, Service for computing quarterly investment achievement rates.  Reads from the (+34 more)

### Community 8 - "Bot Commands & Webhook Spec"
Cohesion: 0.07
Nodes (40): Bot Webhook Commands Requirements Checklist, Bot Command: /help (Command Menu), Bot Command: /q (Quarterly Achievement Rate), Bot Command: /tw (Taiwan Stock Price), Bot Command: /us (US Stock Price), Telegram Webhook API Contract, Decision: Google Sheets CSV Export for Investment Plan, Decision: if/elif Command Dispatch in webhook.py (+32 more)

### Community 9 - "Stock Feature Contracts & Deploy"
Cohesion: 0.09
Nodes (40): Helper: _escape_md() for MarkdownV2, Railway Deployment Platform, Stock Feature API Endpoints Contract, Stock Feature Env Variables Contract, Stock Feature Telegram Message Format Contract, Stock Feature Data Model, Decision: Use APScheduler 3.x, Decision: Centralize Technical Indicator Calculation in indicators.py (+32 more)

### Community 10 - "Portfolio Repository (TW/US)"
Cohesion: 0.11
Nodes (35): fetch_portfolio(), fetch_portfolio_us(), _normalize_us_symbol(), _parse_number(), Repository for reading personal portfolio data from Google Sheets CSV export., Normalize prefixed US symbol text to a ticker.      Args:         raw: Raw sy, Fetch and parse US portfolio rows from Google Sheets CSV export.      Expected, Convert a raw cell string to float.      Handles empty strings, thousand-separ (+27 more)

### Community 11 - "PnL Fetch & Cache"
Cohesion: 0.08
Nodes (18): _fetch_pnl_cell(), fetch_pnl_tw(), fetch_pnl_us(), Fetch a single PnL summary cell from a Google Sheets CSV, with Redis cache., Fetch the TW portfolio total unrealized PnL from cell I20.      Uses Redis cac, Fetch the US portfolio total unrealized PnL from cell H21.      Uses Redis cac, _format_pnl_reply(), get_pnl_reply() (+10 more)

### Community 12 - "API Contracts & Engineering Principles"
Cohesion: 0.13
Nodes (34): API Contracts: fastApiStock, Contract: /pnl Telegram Bot Command, Constitution v1.2.0 (Engineering Principles I-V), Google Sheets CSV Export, investment_plan_repo.py, Structured Logging Middleware, _parse_number() Helper, /pnl Telegram Command (+26 more)

### Community 13 - "Logging Middleware"
Cohesion: 0.1
Nodes (27): BaseHTTPMiddleware, _client_ip(), _level(), LoggingMiddleware, _mask_sensitive(), Structured request/response/performance logging middleware.  Emits three log l, Map HTTP status code to Python logging level.      Args:         status: HTTP, Emit REQ / RES / PERF log lines for every request. (+19 more)

### Community 14 - "Investment Plan Repository"
Cohesion: 0.11
Nodes (27): _dict_to_entry(), _entry_to_dict(), fetch_investment_plan(), _fetch_live(), _parse_date(), _parse_number(), Repository for reading quarterly investment plan data from Google Sheets CSV exp, Serialise an InvestmentPlanEntry to a JSON-safe dict for Redis.      Args: (+19 more)

### Community 15 - "Rate Limit Config"
Cohesion: 0.1
Nodes (21): load_config(), RateLimitConfig, Rate limit configuration loaded from environment variables.  Each route group, Parse TW_STOCKS env var into a list of Taiwan stock codes.      Returns:, Immutable rate limit parameters for one route group.      Attributes:, Parse US_STOCKS env var into a list of uppercased US stock tickers.      Retur, Build the Redis connection URL for the rate-limiter storage backend.      Retu, Build a ``RateLimitConfig`` from environment variables.      Args:         pr (+13 more)

### Community 16 - "Webhook Integration Tests"
Cohesion: 0.32
Nodes (14): _make_update(), _post(), Integration tests for POST /api/v1/webhook/telegram., test_correct_secret_passes(), test_help_command_replies_with_menu(), test_missing_secret_returns_403(), test_non_text_message_ignored(), test_q_command_dispatched() (+6 more)

### Community 17 - "US Stock Repo Tests"
Cohesion: 0.29
Nodes (9): _make_hist(), Tests for the US stock repository., test_empty_history_raises_stock_not_found(), test_price_and_change_calculated(), test_returns_rich_stock_data(), test_symbol_used_without_tw_suffix(), fetch_us_stock(), Repository for fetching US stock data via yfinance.  Mirrors twstock_repo but (+1 more)

### Community 18 - "Railway CI/CD Pipeline"
Cohesion: 0.8
Nodes (5): GitHub Actions CI/CD, Railway Deployment, Tasks: Railway Deployment via GitHub Actions (20260405), Task: Docker Image Build & Railway Deploy via GitHub Actions (20260405), Task: Docker Image Build & Railway Deploy (copy) (20260405)

### Community 19 - "Test Fixtures (fakeredis)"
Cohesion: 0.5
Nodes (3): _fake_redis(), Shared pytest fixtures for the fastapistock test suite., Replace all Redis clients with in-memory fakeredis instances.      Patches the

### Community 20 - "Package Init"
Cohesion: 1.0
Nodes (0):

### Community 21 - "Package Init"
Cohesion: 1.0
Nodes (0):

### Community 22 - "Package Init"
Cohesion: 1.0
Nodes (0):

### Community 23 - "Package Init"
Cohesion: 1.0
Nodes (0):

### Community 24 - "Package Init"
Cohesion: 1.0
Nodes (0):

### Community 25 - "Package Init"
Cohesion: 1.0
Nodes (0):

### Community 26 - "Package Init"
Cohesion: 1.0
Nodes (0):

### Community 27 - "Package Init"
Cohesion: 1.0
Nodes (0):

### Community 28 - "Quickstart Guide"
Cohesion: 1.0
Nodes (1): Google Sheets Public Share Setup Guide

### Community 29 - "Cache Behavior Docs"
Cohesion: 1.0
Nodes (1): Redis Cache Behavior Documentation

## Knowledge Gaps
- **120 isolated node(s):** `Parse TW_STOCKS env var into a list of Taiwan stock codes.      Returns:`, `Parse US_STOCKS env var into a list of uppercased US stock tickers.      Retur`, `Build the Redis connection URL for the rate-limiter storage backend.      Retu`, `APScheduler configuration and scheduled push logic.  Runs inside the FastAPI p`, `Return True when *now* falls in the Taiwan stock push window.      Window: Mon` (+115 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Quickstart Guide`** (1 nodes): `Google Sheets Public Share Setup Guide`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Cache Behavior Docs`** (1 nodes): `Redis Cache Behavior Documentation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get()` connect `Redis Cache Layer` to `Response Envelope & Schemas`, `Portfolio Service & US Stocks`, `Portfolio Repository (TW/US)`, `PnL Fetch & Cache`, `Logging Middleware`, `Investment Plan Repository`, `US Stock Repo Tests`?**
  _High betweenness centrality (0.258) - this node is a cross-community bridge._
- **Why does `RichStockData` connect `Telegram Formatter & Rich Stock` to `Response Envelope & Schemas`, `US Stock Repo Tests`, `Portfolio Service & US Stocks`, `Redis Cache Layer`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Why does `StockNotFoundError` connect `Response Envelope & Schemas` to `US Stock Repo Tests`, `Telegram Formatter & Rich Stock`, `Scheduler & Exception Handlers`?**
  _High betweenness centrality (0.066) - this node is a cross-community bridge._
- **Are the 57 inferred relationships involving `get()` (e.g. with `_validation_exception_handler()` and `_client_ip()`) actually correct?**
  _`get()` has 57 INFERRED edges - model-reasoned connections that need verification._
- **Are the 46 inferred relationships involving `RichStockData` (e.g. with `StockNotFoundError` and `Repository for fetching Taiwan stock data via yfinance.  Handles all external`) actually correct?**
  _`RichStockData` has 46 INFERRED edges - model-reasoned connections that need verification._
- **Are the 37 inferred relationships involving `StockNotFoundError` (e.g. with `Custom exception handlers that return the standard ResponseEnvelope.` and `Return a 404 envelope for unknown stock symbols.      Args:         _request:`) actually correct?**
  _`StockNotFoundError` has 37 INFERRED edges - model-reasoned connections that need verification._
- **Are the 33 inferred relationships involving `StockData` (e.g. with `StockNotFoundError` and `Repository for fetching Taiwan stock data via yfinance.  Handles all external`) actually correct?**
  _`StockData` has 33 INFERRED edges - model-reasoned connections that need verification._
