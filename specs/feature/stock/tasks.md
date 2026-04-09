# Tasks: 定時股票推播排程 + 手動觸發 API

**Input**: Design documents from `/specs/feature/stock/`
**Branch**: `feature/stock`

**Organization**: 3 User Stories，依優先順序實作，共用 Foundational 層。
測試為必要（spec.md 驗收條件第 9 點：覆蓋率 ≥ 80%，時間窗口必測）。

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: 可平行執行（不同檔案，無相互依賴）
- **[Story]**: 對應 user story（US1/US2/US3）
- 每個任務包含精確檔案路徑

---

## Phase 1: Setup（共用基礎設定）

**Purpose**: 新增依賴、更新設定，不涉及業務邏輯

- [ ] T001 在 `pyproject.toml` dependencies 新增 `"apscheduler>=3.10,<4"`，執行 `uv add "apscheduler>=3.10,<4"` 鎖定版本
- [ ] T002 在 `src/fastapistock/config.py` 新增 `TELEGRAM_USER_ID: str`、`tw_stock_codes() -> list[str]`、`us_stock_symbols() -> list[str]` 三個 config 項目，所有值由 `os.getenv()` 讀取

**Checkpoint**: `uv run python -c "from fastapistock.config import tw_stock_codes; print(tw_stock_codes())"` 不拋出例外

---

## Phase 2: Foundational（阻斷性前置基礎）

**Purpose**: `RichStockData` schema、技術指標計算、富格式 Telegram formatter，US1/US2/US3 全部依賴此 phase

**⚠️ CRITICAL**: 所有 user story 均需等此 phase 完成

- [ ] T003 在 `src/fastapistock/schemas/stock.py` 新增 `RichStockData` Pydantic model（20 個欄位：symbol, display_name, market Literal['TW','US'], price, prev_close, change, change_pct, ma20, ma50, rsi, macd, macd_signal, macd_hist, bb_upper, bb_mid, bb_lower, volume, volume_avg20, week52_high, week52_low）；現有 `StockData` 不動
- [ ] T004 建立 `src/fastapistock/services/indicators.py`，實作 `IndicatorResult` frozen dataclass 和 `calculate(hist: pd.DataFrame) -> IndicatorResult`（RSI-14、MACD-12/26/9、MA20、MA50、Bollinger Bands-20/2、volume_avg20、week52_high/low），歷史不足欄位回傳 `None`
- [ ] T005 [P] 在 `src/fastapistock/services/indicators.py` 新增 `ScoreResult` frozen dataclass 和 `score_stock(price: float, change_pct: float, indicators: IndicatorResult) -> ScoreResult`，評分規則依 data-model.md §5 實作（範圍 -8~+8，≥+3 看漲，≤-3 看跌）
- [ ] T006 [P] 建立 `src/fastapistock/services/indicators.py` 內的 `_escape_md(text: str) -> str` helper，escape MarkdownV2 特殊字元（`_ * [ ] ( ) ~ > # + - = | { } . !`）
- [ ] T007 在 `src/fastapistock/services/telegram_service.py` 新增 `format_rich_stock_message(stocks: list[RichStockData], market: Literal['TW', 'US'], now: datetime) -> str`（依 contracts/telegram-message-format.md 規範，使用 MarkdownV2，呼叫 `_escape_md`）
- [ ] T008 在 `src/fastapistock/services/telegram_service.py` 新增 `send_rich_stock_message(user_id: str, stocks: list[RichStockData], market: Literal['TW', 'US']) -> bool`，使用 `parse_mode='MarkdownV2'`，timeout=10 s
- [ ] T009 [P] 建立 `tests/test_indicators.py`，測試：`calculate()` 給定 60 列 OHLCV DataFrame 回傳正確 RSI/MACD/MA/BB；歷史不足 20 列時 bb_upper 為 None；`score_stock()` RSI<30 得分 +2；`score_stock()` MACD hist>0 且 MACD>0 得分 +2；金叉看漲 score≥3 回傳 verdict='看漲'
- [ ] T010 [P] 建立 `tests/test_telegram_formatter.py`，測試：`format_rich_stock_message()` 對台股輸出含 `*台股定時推播*`；對美股輸出含 `*美股定時推播*`；特殊字元（如 `+2.30`）被正確 escape；RSI 欄位為 None 時對應行不出現在輸出中

**Checkpoint**: `uv run pytest tests/test_indicators.py tests/test_telegram_formatter.py -v` 全部 PASS

---

## Phase 3: US1 - 升級台股手動推播 API（Priority: P1）🎯 MVP

**Goal**: `/api/v1/tgMessage/{id}?stock=0050,2330` 改回傳包含 RSI/MACD/均線/布林/評分的 MarkdownV2 Telegram 訊息

**Independent Test**: `curl "http://localhost:8000/api/v1/tgMessage/CHAT_ID?stock=0050"` 後在 Telegram 收到含 RSI 欄位的格式化訊息

### Implementation: US1

- [ ] T011 [US1] 在 `src/fastapistock/repositories/twstock_repo.py` 新增 `fetch_tw_rich_stock(code: str) -> RichStockData`，使用 `yf.Ticker(symbol).history(period='6mo')` 取 6 個月資料，呼叫 `indicators.calculate(hist)` 填充技術指標；現有 `fetch_stock()` 不修改
- [ ] T012 [US1] 在 `src/fastapistock/services/stock_service.py` 新增 `get_rich_tw_stock(code: str) -> RichStockData` 和 `get_rich_tw_stocks(codes: list[str]) -> list[RichStockData]`，cache key 用 `rich_tw:{code}:{date}`（TTL=300 s），並行抓取 cache miss（複用現有 ThreadPoolExecutor 模式）
- [ ] T013 [US1] 修改 `src/fastapistock/routers/telegram.py` 的 `send_telegram_stock_info()`，將 `get_stocks()` 改為 `get_rich_tw_stocks()`，`send_stock_message()` 改為 `send_rich_stock_message(id, stocks, market='TW')`；path/query params/response envelope 不變
- [ ] T014 [US1] 建立 `tests/test_tw_telegram_rich.py`，mock `get_rich_tw_stocks` 和 `send_rich_stock_message`，測試：正常台股代碼回傳 `{"status": "success"}`；非數字代碼（如 "abc"）被過濾回傳 `{"status": "error"}`；空 stock 參數回傳 error；`send_rich_stock_message` 被呼叫時 market='TW'

**Checkpoint**: `curl "http://localhost:8000/api/v1/tgMessage/TEST_ID?stock=0050"` → `{"status":"success"}` 且 Telegram 收到含技術分析的 MarkdownV2 訊息

---

## Phase 4: US2 - 新增美股手動推播 API（Priority: P2）

**Goal**: `GET /api/v1/usMessage/{id}?stock=AAPL,NVDA` 推送美股技術分析到 Telegram

**Independent Test**: `curl "http://localhost:8000/api/v1/usMessage/CHAT_ID?stock=AAPL"` 後在 Telegram 收到含 RSI 的美股格式訊息

### Implementation: US2

- [ ] T015 [P] [US2] 建立 `src/fastapistock/repositories/us_stock_repo.py`，實作 `fetch_us_stock(symbol: str) -> RichStockData`：random sleep 0.1–0.5 s；`yf.Ticker(symbol).history(period='6mo', timeout=10)`；空 DataFrame 拋出 `StockNotFoundError`；呼叫 `indicators.calculate(hist)`；market='US'
- [ ] T016 [P] [US2] 建立 `src/fastapistock/services/us_stock_service.py`，實作 `get_us_stock(symbol: str) -> RichStockData` 和 `get_us_stocks(symbols: list[str]) -> list[RichStockData]`，cache key `us_stock:{symbol}:{date}`（TTL=300 s），並行抓取 cache miss
- [ ] T017 [US2] 建立 `src/fastapistock/routers/us_telegram.py`，定義 `router = APIRouter(prefix='/api/v1/usMessage', tags=['us-telegram'])` 和 `send_us_telegram_stock_info()`，ticker 過濾規則：strip + upper + `isalpha()` 過濾非英文字母；呼叫 `get_us_stocks()` + `send_rich_stock_message(id, stocks, market='US')`
- [ ] T018 [US2] 在 `src/fastapistock/main.py` 的 `create_app()` 中 include `us_telegram.router`
- [ ] T019 [US2] 建立 `tests/test_us_telegram.py`，mock `get_us_stocks` 和 `send_rich_stock_message`，測試：正常 ticker 回傳 success；小寫 `aapl` 自動轉大寫成功；含數字的 ticker（`AAP1`）被過濾回傳 error；空 stock 回傳 error；market='US' 被正確傳遞
- [ ] T020 [P] [US2] 建立 `tests/test_us_stock_repo.py`，mock `yfinance.Ticker`，測試：正常抓取回傳 `RichStockData`；empty DataFrame 拋出 `StockNotFoundError`；symbol 不加 `.TW` suffix（`AAPL` 保持 `AAPL`）

**Checkpoint**: `curl "http://localhost:8000/api/v1/usMessage/TEST_ID?stock=AAPL"` → `{"status":"success"}` 且 Telegram 收到美股技術分析訊息

---

## Phase 5: US3 - APScheduler 定時排程推播（Priority: P3）

**Goal**: FastAPI 啟動後自動每 30 分鐘依時間窗口推播台股（周一~五 08:30–14:00）或美股（周一~六 17:00–04:00）到 TELEGRAM_USER_ID

**Independent Test**: 啟動服務後 log 出現 `APScheduler started`；手動修改系統時間到 09:00 周一驗證台股推播觸發

### Implementation: US3

- [ ] T021 建立 `src/fastapistock/scheduler.py`，實作 `is_tw_market_window(now: datetime) -> bool`（Asia/Taipei 周一~五 08:30–14:00）和 `is_us_market_window(now: datetime) -> bool`（周一~五 ≥17:00 或 周二~六 ≤04:00）；使用 `zoneinfo.ZoneInfo('Asia/Taipei')`
- [ ] T022 [US3] 在 `src/fastapistock/scheduler.py` 建立 `push_tw_stocks() -> None` 和 `push_us_stocks() -> None`（從 config 讀取 codes/symbols，呼叫 `get_rich_tw_stocks/get_us_stocks`，再呼叫 `send_rich_stock_message(TELEGRAM_USER_ID, ...)`，整個函式 wrap 在 try/except + logger.exception，不 re-raise）
- [ ] T023 [US3] 在 `src/fastapistock/scheduler.py` 建立 `_scheduled_push() -> None` 和 `build_scheduler() -> AsyncIOScheduler`（`IntervalTrigger(minutes=30, timezone='Asia/Taipei')`，job 為 `_scheduled_push`）
- [ ] T024 [US3] 修改 `src/fastapistock/main.py`：新增 `@asynccontextmanager async def lifespan(app: FastAPI)`，在 startup 呼叫 `build_scheduler().start()`，在 shutdown 呼叫 `scheduler.shutdown(wait=False)`；`create_app()` 加入 `lifespan=lifespan`
- [ ] T025 [P] [US3] 建立 `tests/test_scheduler.py`，使用 `freezegun.freeze_time` 或直接傳入 `datetime` 物件，測試 12 個邊界案例（依 quickstart.md §關鍵測試案例）：08:30 在台股窗口；08:29 不在；14:00 在台股窗口；14:01 不在；周六 09:00 不在台股窗口；17:00 周三在美股窗口；04:00 周四在美股窗口；04:01 不在；周日 20:00 不在；周六 03:00 在（周五夜延伸）；周六 05:00 不在；周一 03:00 不在美股窗口（周日夜無效）

**Checkpoint**: `uv run uvicorn fastapistock.main:app` 啟動後 log 出現 `APScheduler started`；`uv run pytest tests/test_scheduler.py -v` 12 個案例全 PASS

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 確保全部測試通過、程式碼品質達標

- [ ] T026 [P] 執行 `uv run ruff check . --fix && uv run ruff format .`，修正所有 linting 問題（重點：新增檔案的 import 順序、行長度、單引號）
- [ ] T027 [P] 執行 `uv run mypy src/`，修正型別錯誤（重點：`Literal['TW','US']` 傳遞正確、`float | None` 欄位處理、`zoneinfo` import）
- [ ] T028 執行 `uv run pytest --cov=src --cov-report=term-missing`，確認整體覆蓋率 ≥ 80%；補充不足覆蓋的邏輯路徑

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)
    ↓
Phase 2 (Foundational) ← CRITICAL，阻斷所有 US
    ↓           ↓           ↓
Phase 3 (US1)  Phase 4 (US2)  Phase 5 (US3)
    ↓           ↓           ↓
              Phase 6 (Polish)
```

- **Phase 1**: 無依賴，立即開始
- **Phase 2**: 依賴 Phase 1 完成，阻斷 US1/US2/US3
- **Phase 3 (US1)**: 依賴 Phase 2；T011 → T012 → T013；T014 可平行 T011
- **Phase 4 (US2)**: 依賴 Phase 2；T015/T016 可平行；T017 依賴 T015+T016；T018 依賴 T017
- **Phase 5 (US3)**: 依賴 Phase 2 + Phase 3 (US1) 的 get_rich_tw_stocks；T021 → T022 → T023 → T024
- **Phase 6**: 依賴所有 US phase 完成

### User Story 內部相依

```
US1: T011 → T012 → T013
              ↗
     T014 [可平行 T011 開始]

US2: T015 ──┐
     T016 ──┼→ T017 → T018
     T019/T020 [可平行上述]

US3: T021 → T022 → T023 → T024
     T025 [可平行 T021 開始，freezegun mock]
```

### Phase 3、4 可平行條件

Phase 2 完成後，**US1 和 US2 可同步進行**：
- US1 改的是 `telegram.py` router（現有）
- US2 建的是 `us_telegram.py`（全新）
- 兩者不共用同一目標檔案

---

## Parallel Example: Phase 2

```
可同時執行（不同檔案）：
  T004 → src/fastapistock/services/indicators.py  (calculate)
  T005 → src/fastapistock/services/indicators.py  (score_stock) ← 等 T004 完成
  T006 → src/fastapistock/services/indicators.py  (_escape_md)

  T007 → src/fastapistock/services/telegram_service.py (format)
  T008 → src/fastapistock/services/telegram_service.py (send)

  T009 → tests/test_indicators.py
  T010 → tests/test_telegram_formatter.py
```

## Parallel Example: US2

```
可同時執行：
  T015 → src/fastapistock/repositories/us_stock_repo.py
  T016 → src/fastapistock/services/us_stock_service.py
  T019 → tests/test_us_telegram.py
  T020 → tests/test_us_stock_repo.py
```

---

## Implementation Strategy

### MVP：只完成 US1（台股富格式手動推播）

1. Phase 1: Setup（T001-T002）
2. Phase 2: Foundational（T003-T010）
3. Phase 3: US1（T011-T014）
4. **STOP & VALIDATE**：`curl /api/v1/tgMessage/ID?stock=0050`，Telegram 確認收到 MarkdownV2 格式
5. 推上 Railway，確認生產環境正常

### Incremental Delivery

```
MVP（Phase 1-3）→ 台股手動推播升級完成
  ↓
加 Phase 4（US2）→ 美股手動推播上線 → 可隨時查詢美股
  ↓
加 Phase 5（US3）→ 全自動定時推播 → 不需手動觸發
  ↓
Phase 6 Polish → 品質保證
```

---

## Notes

- 測試全部採用 mock，不呼叫真實 yfinance / Telegram API
- `freezegun` 用於時間窗口測試；若尚未安裝，執行 `uv add --group dev freezegun`
- `_escape_md()` 務必在 formatter 測試（T010）中驗證，MarkdownV2 格式錯誤會讓 Telegram 拒絕整則訊息
- `RichStockData.market` 欄位需用 `Literal['TW', 'US']`（from `typing`），mypy 才能通過
- `StockNotFoundError` 共用 `repositories/twstock_repo.py` 現有定義，`us_stock_repo.py` 直接 import
- Railway Variables 設定完成後，`TELEGRAM_USER_ID` 為空字串時 `push_tw/us_stocks()` 應 log warning 並提早 return，避免送出 chat_id 為空的 Telegram 請求
