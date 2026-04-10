# Tasks: Telegram Bot Webhook with Command Menu & Quarterly Investment Achievement Rate

**Input**: Design documents from `/specs/003-bot-webhook-commands/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/webhook.md ✅

**Organization**: 任務依 User Story 分組，每個 Story 可獨立實作與驗證。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無依賴）
- **[Story]**: 對應 spec.md 的 User Story（US1–US5）

---

## Phase 1: Setup（環境設定）

**Purpose**: 新增環境變數設定，不影響現有功能

- [ ] T001 在 `src/fastapistock/config.py` 新增 `GOOGLE_SHEETS_INVESTMENT_PLAN_GID` 與 `TELEGRAM_WEBHOOK_SECRET` 兩個 env var 讀取（參考現有 `GOOGLE_SHEETS_PORTFOLIO_GID_US` 寫法）
- [ ] T002 在 `.env.example`（若存在）或專案文件中記錄兩個新 env var 的說明與預設值

---

## Phase 2: Foundational（共用基礎設施）

**Purpose**: 所有 User Story 共用的基礎元件，**必須在所有 Story 開始前完成**

**⚠️ CRITICAL**: US1–US5 均依賴本階段完成

- [ ] T003 在 `src/fastapistock/services/telegram_service.py` 新增 `reply_to_chat(chat_id: str, text: str) -> bool` helper，使用現有 `_TELEGRAM_API_BASE`、`_REQUEST_TIMEOUT` 與 `TELEGRAM_TOKEN`
- [ ] T004 [P] 在 `src/fastapistock/routers/webhook.py` 建立 Pydantic models：`TelegramFrom`、`TelegramChat`、`TelegramMessage`、`TelegramUpdate`（欄位詳見 `data-model.md`，注意 `from_` 欄位需 `alias="from"`）
- [ ] T005 [P] 在 `src/fastapistock/middleware/rate_limit/config.py` 說明（或在 `.env.example` 中）新增 `RATE_LIMIT_WEBHOOK_*` 系列變數的文件，確保 webhook endpoint 套用獨立 rate limit 設定

**Checkpoint**: 基礎元件就緒，可開始 US1–US5 實作

---

## Phase 3: User Story 1 - 季度投資達成率 `/q`（Priority: P1）🎯 MVP

**Goal**: 用戶傳送 `/q` 後，Bot 從 Google Sheets 計算當季投資達成率並回覆

**Independent Test**: 傳送 `/q` 給 Bot，確認回覆包含達成率百分比、已投入金額、預期金額、股票代號列表

### 測試：User Story 1（TDD - 先寫測試確認失敗）

- [ ] T006 [P] [US1] 在 `tests/unit/test_investment_plan_repo.py` 撰寫 `fetch_investment_plan` 的單元測試：正常解析、空白欄位跳過、日期格式失敗跳過、Redis cache hit/miss、Redis 不可用時 fallback live fetch
- [ ] T007 [P] [US1] 在 `tests/unit/test_investment_plan_service.py` 撰寫 `get_quarterly_achievement_rate` 的單元測試：正常計算、無當季資料、分母為零、超額達成（>100%）

### 實作：User Story 1

- [ ] T008 [US1] 在 `src/fastapistock/repositories/investment_plan_repo.py` 實作 `InvestmentPlanEntry` dataclass（frozen）與 `fetch_investment_plan(today: date) -> list[InvestmentPlanEntry]`：讀取 `GOOGLE_SHEETS_ID` + `GOOGLE_SHEETS_INVESTMENT_PLAN_GID` CSV；日期欄（B=index 1, C=index 2）解析；數字欄（F=index 5, G=index 6）解析；Redis cache key `investment_plan:{YYYY-MM-DD}`，TTL `PORTFOLIO_CACHE_TTL`；Redis 不可用時 graceful fallback（depends on T006）
- [ ] T009 [US1] 在 `src/fastapistock/services/investment_plan_service.py` 實作 `get_quarterly_achievement_rate(today: date) -> QuarterlyAchievementReport | None` 與 `format_achievement_reply(report: QuarterlyAchievementReport | None) -> str`：篩選當季行（start_date ≤ today ≤ end_date）；達成率計算；進度條格式化（▓/░ 10格）；分母為零與無資料的錯誤訊息（depends on T007, T008）
- [ ] T010 [US1] 在 `src/fastapistock/routers/webhook.py` 建立 `APIRouter(prefix='/api/v1/webhook', tags=['webhook'])` 與 `POST /telegram` endpoint：驗證 `X-Telegram-Bot-Api-Secret-Token` header；靜默忽略非授權 user_id（HTTP 200）；解析 `TelegramUpdate`；dispatch `/q` 指令至 `investment_plan_service`；呼叫 `reply_to_chat()` 回覆（depends on T003, T004, T009）
- [ ] T011 [US1] 在 `src/fastapistock/main.py` 的 `create_app()` 中 `include_router(webhook.router)`；在 `_lifespan` startup 中新增呼叫 `setMyCommands`（4 個指令：`q`, `us`, `tw`, `help`）（depends on T010）
- [ ] T012 [US1] 在 `tests/integration/test_webhook.py` 撰寫 `/q` 端點整合測試：正確 secret + 授權 user_id 回 200；錯誤 secret 回 403；非授權 user_id 回 200（靜默）（depends on T010）

**Checkpoint**: 此時 `/q` 指令應可完整運作並獨立驗證

---

## Phase 4: User Story 2 - 美股報價 `/us`（Priority: P2）

**Goal**: 用戶傳送 `/us AAPL,TSLA` 後，Bot 回覆美股即時報價

**Independent Test**: 傳送 `/us AAPL` 給 Bot，確認回覆包含 Apple 股價資訊

### 實作：User Story 2

- [ ] T013 [US2] 在 `src/fastapistock/routers/webhook.py` 的 `POST /telegram` handler 新增 `/us` dispatch 邏輯：解析 ticker 參數（同 `us_telegram.py` 的 `isalpha()` 過濾）；無參數時回覆使用說明；呼叫 `get_us_stocks()` 並格式化後用 `reply_to_chat()` 回覆（depends on T010）
- [ ] T014 [US2] 在 `tests/integration/test_webhook.py` 補充 `/us` 指令測試：有效 ticker 回報价、無效 ticker 回錯誤、無參數回使用說明（depends on T013）

**Checkpoint**: `/us` 指令獨立可用

---

## Phase 5: User Story 3 - 台股報價 `/tw`（Priority: P3）

**Goal**: 用戶傳送 `/tw 0050,2330` 後，Bot 回覆台股即時報價

**Independent Test**: 傳送 `/tw 2330` 給 Bot，確認回覆包含台積電股價資訊

### 實作：User Story 3

- [ ] T015 [US3] 在 `src/fastapistock/routers/webhook.py` 的 `POST /telegram` handler 新增 `/tw` dispatch 邏輯：解析 code 參數（同 `telegram.py` 的 `isdigit()` 過濾）；無參數時回覆使用說明；呼叫 `get_rich_tw_stocks()` 並格式化後用 `reply_to_chat()` 回覆（depends on T010）
- [ ] T016 [US3] 在 `tests/integration/test_webhook.py` 補充 `/tw` 指令測試：有效代號回報價、無效代號回錯誤、無參數回使用說明（depends on T015）

**Checkpoint**: `/tw` 指令獨立可用

---

## Phase 6: User Story 4 - 指令選單 `/help`（Priority: P4）

**Goal**: 用戶傳送 `/help` 後，Bot 回覆所有可用指令清單

**Independent Test**: 傳送 `/help`，確認回覆包含 `/q`、`/us`、`/tw`、`/help` 四個指令說明

### 實作：User Story 4

- [ ] T017 [US4] 在 `src/fastapistock/routers/webhook.py` 的 `POST /telegram` handler 新增 `/help` dispatch 邏輯：回覆靜態指令說明文字（格式見 `contracts/webhook.md`）（depends on T010）

**Checkpoint**: 四個指令（`/q`, `/us`, `/tw`, `/help`）均可獨立使用

---

## Phase 7: User Story 5 - 排程主動推送（Priority: P5）

**Goal**: 確認現有排程推送功能在新增 webhook 後不受影響

**Independent Test**: 觸發現有排程，確認仍正常推送（不受 webhook router 干擾）

### 驗證：User Story 5

- [ ] T018 [US5] 執行 `uv run pytest tests/` 確認現有 scheduler 相關測試全數通過（無需修改任何 scheduler 相關程式碼）

**Checkpoint**: 排程推送與 webhook 指令查詢兩條路徑均正常運作

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: 安全強化、程式碼品質、最終驗證

- [ ] T019 [P] 在 `tests/integration/test_webhook.py` 補充安全邊界測試：未授權 user_id 完全靜默（不回應 Telegram）；缺少 secret header 回 403；非文字訊息（`text=None`）靜默忽略
- [ ] T020 [P] 執行 `uv run ruff check . --fix && uv run ruff format .` 確認所有新增程式碼通過 lint
- [ ] T021 [P] 執行 `uv run mypy src/` 確認所有新增程式碼通過嚴格型別檢查
- [ ] T022 執行 `uv run pytest --cov=fastapistock --cov-report=term-missing` 確認整體覆蓋率 ≥ 80%
- [ ] T023 執行 `uv run pre-commit run --all-files` 確認所有 pre-commit hooks 通過

---

## Dependencies & Execution Order

### Phase 依賴關係

```
Phase 1 (Setup)
    └── Phase 2 (Foundational) ─ BLOCKS 所有 User Stories
            ├── Phase 3 (US1 - /q)          ← 核心，需先完成
            │       └── Phase 4 (US2 - /us) ← webhook.py 已存在後可平行
            │       └── Phase 5 (US3 - /tw) ← 同上
            │       └── Phase 6 (US4 - /help) ← 同上
            └── Phase 7 (US5 - 排程驗證)   ← 獨立，任何時候可執行
Phase 8 (Polish) ─ 依賴所有 Story 完成
```

### US2/US3/US4 相互依賴說明

- T013, T015, T017 均修改同一個 `webhook.py` 的 dispatch 邏輯
- **建議循序執行**（T013 → T015 → T017），避免同一檔案衝突
- 若平行執行，需在不同 function/section 操作並手動合併

### Within Each User Story

```
測試（T006/T007）→ Repo（T008）→ Service（T009）→ Router（T010）→ main.py（T011）→ 整合測試（T012）
```

### Parallel Opportunities

```bash
# Phase 2 可平行執行的任務：
T003 (telegram_service helper)
T004 (Pydantic models)
T005 (rate limit 文件)

# Phase 3 測試可先平行撰寫（TDD）：
T006 (repo unit tests)
T007 (service unit tests)

# Phase 8 可平行執行：
T019 (security tests)
T020 (ruff)
T021 (mypy)
```

---

## Parallel Example: User Story 1

```bash
# 先同步執行（TDD 紅燈階段）：
T006: tests/unit/test_investment_plan_repo.py
T007: tests/unit/test_investment_plan_service.py

# 確認測試失敗後，循序實作：
T008 → T009 → T010 → T011

# 最後整合測試：
T012: tests/integration/test_webhook.py
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 1: Setup（T001–T002）
2. 完成 Phase 2: Foundational（T003–T005）
3. 完成 Phase 3: User Story 1（T006–T012）
4. **STOP & VALIDATE**：傳送 `/q` 給 Bot，確認達成率回覆正確
5. 可部署、展示 MVP

### Incremental Delivery

1. MVP：`/q` 達成率查詢 → 部署
2. 加入：`/us` 美股查詢 → 測試 → 部署
3. 加入：`/tw` 台股查詢 → 測試 → 部署
4. 加入：`/help` 選單 → 部署
5. 驗證：排程推送無回歸
6. Polish：ruff + mypy + 安全測試

---

## Notes

- [P] 任務 = 不同檔案或完全獨立，無依賴問題
- [Story] 標籤對應 spec.md 的 User Story（US1–US5）
- T006/T007 為 TDD 測試，**必須先寫且確認失敗**，再開始 T008/T009
- Telegram webhook 要求所有情境（含靜默忽略）均回傳 HTTP 200
- `setMyCommands` 在 startup 冪等執行，不影響效能
- `reply_to_chat()` 複用現有 `_TELEGRAM_API_BASE`，不引入新 HTTP 客戶端
