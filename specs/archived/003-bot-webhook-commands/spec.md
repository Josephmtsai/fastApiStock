# Feature Specification: Telegram Bot Webhook with Command Menu & Quarterly Investment Achievement Rate

**Feature Branch**: `003-bot-webhook-commands`
**Created**: 2026-04-10
**Status**: Draft
**Input**: User description: "請依照剛剛講的開始設計spec 排程還是要可以主動推送 新增你剛剛說的指令以及指令清單"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Query Quarterly Investment Achievement Rate (Priority: P1)

A user sends `/q` to the Telegram bot. The bot looks up the quarterly investment plan sheet (Google Sheets), filters rows where today falls between the start date and end date, then replies with the achievement rate (already invested ÷ expected investment × 100%), total invested, total expected, and the list of stock symbols for the current quarter.

**Why this priority**: This is the core new feature that prompted the entire effort. All other commands are improvements built around it.

**Independent Test**: Can be fully tested by sending `/q` to the bot and verifying the reply contains a percentage, dollar amounts, and stock tickers matching the current quarter rows in the sheet.

**Acceptance Scenarios**:

1. **Given** at least one sheet row has a date range covering today, **When** the user sends `/q`, **Then** the bot replies with the overall achievement rate as a percentage, total invested USD, total expected USD, and a per-symbol breakdown showing each stock's individual rate, invested amount, and expected amount.
2. **Given** no sheet row covers today's date, **When** the user sends `/q`, **Then** the bot replies with a friendly message indicating no active quarter data was found.
3. **Given** the user is not the authorized user, **When** `/q` is sent, **Then** the bot does not reply (message is silently ignored).

---

### User Story 2 - Query US Stock Price via Bot (Priority: P2)

A user sends `/us AAPL,TSLA` to the bot and receives an immediate real-time price summary for those US tickers.

**Why this priority**: Existing functionality exposed through scheduled push; surfacing it via interactive bot command improves usability and unifies the interface.

**Independent Test**: Can be tested independently by sending `/us AAPL` and verifying the reply contains price data for Apple.

**Acceptance Scenarios**:

1. **Given** valid US ticker symbols, **When** the user sends `/us AAPL,TSLA`, **Then** the bot replies with formatted price information for each ticker.
2. **Given** an invalid or unrecognized ticker, **When** `/us INVALID` is sent, **Then** the bot replies with an error message indicating the ticker was not found.
3. **Given** no ticker is provided, **When** the user sends `/us` without arguments, **Then** the bot replies with usage guidance.

---

### User Story 3 - Query Taiwan Stock Price via Bot (Priority: P3)

A user sends `/tw 0050,2330` to the bot and receives a price summary for those Taiwan stock codes.

**Why this priority**: Mirrors the US stock command for the Taiwan market; reuses existing logic.

**Independent Test**: Can be tested by sending `/tw 2330` and verifying the reply contains TSMC price data.

**Acceptance Scenarios**:

1. **Given** valid Taiwan stock codes, **When** the user sends `/tw 2330`, **Then** the bot replies with formatted price information for that stock.
2. **Given** an invalid stock code, **When** `/tw 9999` is sent, **Then** the bot replies with a stock-not-found error message.
3. **Given** no code is provided, **When** the user sends `/tw` without arguments, **Then** the bot replies with usage guidance.

---

### User Story 4 - View Help / Command Menu (Priority: P4)

A user sends `/help` and receives a list of all available commands with brief descriptions.

**Why this priority**: Discoverability support; low effort, high value for new or infrequent users.

**Independent Test**: Can be tested by sending `/help` and verifying all four commands appear in the reply with descriptions.

**Acceptance Scenarios**:

1. **Given** any state, **When** the user sends `/help`, **Then** the bot replies with a formatted list of all supported commands (`/q`, `/us`, `/tw`, `/help`) and their usage.

---

### User Story 5 - Scheduled Proactive Push (Priority: P5)

The existing scheduler continues to proactively push stock summaries to the configured user at scheduled times without any user interaction, operating independently of the webhook command flow.

**Why this priority**: Preserves existing behavior; no regression. Scheduler and webhook are independent entry points that must coexist.

**Independent Test**: Can be tested by verifying scheduled jobs still fire and deliver messages at configured intervals after webhook changes are deployed.

**Acceptance Scenarios**:

1. **Given** a configured schedule, **When** the scheduled time arrives, **Then** the bot sends the configured stock summary to the user without any user-initiated command.
2. **Given** the webhook endpoint is active, **When** the scheduler fires, **Then** the scheduled push is unaffected (no interference between the two flows).

---

### Edge Cases

- What happens when the Google Sheets investment plan cannot be fetched (network error, invalid GID)?
- What happens when column F or G contains blank or non-numeric values in the sheet?
- What if a sheet row's start date or end date is malformed or in an unexpected format?
- What if the same stock symbol appears in multiple rows within the same quarter?
- What if the bot receives a message from an unauthorized user?
- What if `/us` or `/tw` receives a very long list of symbols that exceeds Telegram message size limits?
- What if column F sums to zero (division by zero in achievement rate)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose a webhook endpoint that receives incoming Telegram bot messages.
- **FR-002**: System MUST only process messages from the configured authorized Telegram user ID; all other senders MUST be silently ignored.
- **FR-003**: System MUST validate the incoming webhook request using a secret token to reject unauthorized calls.
- **FR-004**: System MUST handle the `/q` command by fetching the investment plan sheet, filtering rows where today falls within the row's start-to-end date range, computing the achievement rate, and replying to the sender.
- **FR-005**: System MUST handle the `/us <tickers>` command by fetching US stock price data and replying with a formatted summary.
- **FR-006**: System MUST handle the `/tw <codes>` command by fetching Taiwan stock price data and replying with a formatted summary.
- **FR-007**: System MUST handle the `/help` command by replying with a list of all supported commands and their usage syntax.
- **FR-008**: System MUST silently ignore unrecognized messages without replying.
- **FR-009**: System MUST register the supported commands (`/q`, `/us`, `/tw`, `/help`) with Telegram so they appear in the bot's native command menu.
- **FR-010**: System MUST continue to support the existing scheduled proactive push mechanism without modification.
- **FR-011**: System MUST cache the investment plan sheet data to avoid repeated fetches within a configurable time window.
- **FR-012**: Achievement rate MUST be computed as `sum(column G) / sum(column F) × 100%` for all rows where today falls within `[column B, column C]` inclusive.
- **FR-013**: When `/us` or `/tw` is sent without arguments, the system MUST reply with usage guidance for that command.
- **FR-014**: When column F sums to zero for the current quarter, the system MUST reply with a message indicating no investment target is set rather than attempting division.
- **FR-015**: The `/q` reply MUST include a per-symbol breakdown showing each stock's individual achievement rate (column G / column F × 100%), invested amount, and expected amount alongside the aggregate totals.

### Key Entities

- **InvestmentPlanEntry**: A single row from the quarterly plan sheet. Key attributes: stock symbol (column A), start date (column B), end date (column C), expected investment in USD (column F), already invested in USD (column G).
- **TelegramUpdate**: An incoming event from Telegram containing chat ID, sender user ID, and message text.
- **BotCommand**: A recognized command string (`/q`, `/us`, `/tw`, `/help`) parsed from a Telegram message, optionally followed by arguments.
- **QuarterlyAchievementReport**: Computed result containing achievement rate %, total invested USD, total expected USD, matched stock symbols, and active date range.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The bot responds to all recognized commands (`/q`, `/us`, `/tw`, `/help`) within 5 seconds under normal conditions.
- **SC-002**: The `/q` command correctly filters only rows whose date range includes today, with zero incorrect inclusions or exclusions.
- **SC-003**: The achievement rate calculation is accurate to two decimal places at both aggregate and per-symbol levels.
- **SC-004**: Messages from unauthorized users are never replied to (0% unauthorized reply rate).
- **SC-005**: The scheduled proactive push continues to function correctly with no regressions after webhook changes are deployed.
- **SC-006**: Investment plan sheet data is not fetched more than once per cache TTL window, even under multiple rapid `/q` requests.

## Assumptions

- The Google Sheets investment plan uses GID `1192950573`; the sheet ID is the same as the existing `GOOGLE_SHEETS_ID` environment variable.
- Column B (start date) and column C (end date) are formatted as `YYYY-MM-DD` or another standard date format parseable without locale-specific configuration.
- Column F (expected USD) and column G (invested USD) may contain comma-formatted numbers (e.g., `1,000.00`); the system will strip commas before parsing.
- Only one Telegram user ID is authorized (the existing `TELEGRAM_USER_ID` config value); multi-user support is out of scope for this feature.
- The Telegram bot token is already configured and the bot is operational.
- The existing GET endpoints for proactive push (`/api/v1/tgMessage`, `/api/v1/usMessage`) remain unchanged and are used exclusively by the scheduler.
- Cache TTL for investment plan sheet data reuses the existing `PORTFOLIO_CACHE_TTL` configuration (default 1 hour).
- A new environment variable `TELEGRAM_WEBHOOK_SECRET` will be added to secure the webhook endpoint.
- The `setMyCommands` Telegram API call to register the command menu is performed once at application startup.
- Rows in the investment plan sheet where both column F and column G are zero or blank are skipped in the achievement rate calculation.
