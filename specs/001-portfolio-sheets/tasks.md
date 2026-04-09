# Tasks: Google Sheets 持倉整合

**Input**: Design documents from `/specs/001-portfolio-sheets/`
**Branch**: `001-portfolio-sheets`

**Organization**: 2 User Stories，依優先順序實作，共用 Setup + Foundational 層。
US1 完成即可上線（持倉顯示），US2 加入快取優化。

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: 可平行執行（不同檔案，無相互依賴）
- **[Story]**: 對應 user story（US1/US2）
- 每個任務包含精確檔案路徑

---

## Phase 1: Setup（共用基礎設定）

**Purpose**: 新增環境變數設定，不涉及業務邏輯

- [X] T001 在 `src/fastapistock/config.py` 新增三個設定項：
  `GOOGLE_SHEETS_ID: str = os.getenv('GOOGLE_SHEETS_ID', '')`、
  `GOOGLE_SHEETS_PORTFOLIO_GID: str = os.getenv('GOOGLE_SHEETS_PORTFOLIO_GID', '')`、
  `PORTFOLIO_CACHE_TTL: int = int(os.getenv('PORTFOLIO_CACHE_TTL', '3600'))`

**Checkpoint**: `uv run python -c "from fastapistock.config import PORTFOLIO_CACHE_TTL; print(PORTFOLIO_CACHE_TTL)"` 印出 3600

---

## Phase 2: Foundational（阻斷性前置基礎）

**Purpose**: `RichStockData` schema 擴充，US1/US2 全部依賴此 phase

**⚠️ CRITICAL**: 所有 user story 均需等此 phase 完成

- [X] T002 在 `src/fastapistock/schemas/stock.py` 的 `RichStockData` 新增三個可選欄位（docstring 同步更新，現有欄位不動）：
  `avg_cost: float | None = None`、
  `unrealized_pnl: float | None = None`、
  `shares: int | None = None`

**Checkpoint**: `uv run python -c "from fastapistock.schemas.stock import RichStockData; r = RichStockData(symbol='T', display_name='x', market='TW', price=100, prev_close=99, change=1, change_pct=1.0, ma20=98, volume=1000, volume_avg20=800); assert r.avg_cost is None"` 無例外

---

## Phase 3: US1 - 台股推播附帶持倉資訊（Priority: P1）🎯 MVP

**Goal**: 台股 Telegram 推播訊息中，持有股票自動附加持倉區塊（平均成本、損益）

**Independent Test**: `curl "http://localhost:8000/api/v1/tgMessage/CHAT_ID?stock=2330"`，
Telegram 收到含「持倉」區塊的 MarkdownV2 訊息（若 2330 在試算表中）；
未持有的股票不顯示持倉區塊；試算表不可達時技術指標仍正常推送

### Implementation: US1

- [X] T003 [US1] 建立 `src/fastapistock/repositories/portfolio_repo.py`，實作：
  - `PortfolioEntry` frozen dataclass（symbol, shares: int, avg_cost: float, unrealized_pnl: float）
  - `_parse_number(raw: str) -> float`：strip 空白、移除千分位逗號、轉 float，空字串回傳 0.0
  - `fetch_portfolio() -> dict[str, PortfolioEntry]`：
    (1) 若 `GOOGLE_SHEETS_ID` 或 `GOOGLE_SHEETS_PORTFOLIO_GID` 為空 → log warning → return {}；
    (2) `httpx.get(CSV export URL, timeout=10, follow_redirects=True)`；
    (3) HTTP 錯誤 → log error → return {}；RequestError → log error → return {}；
    (4) 解析 CSV：略過第一列（標題），略過 A 欄非數字的列，
    取 A(_COL_SYMBOL=0)、C(_COL_SHARES=2)、F(_COL_AVG_COST=5)、I(_COL_UNREALIZED_PNL=8)

- [X] T004 [P] [US1] 建立 `tests/test_portfolio_repo.py`，mock `httpx.get`，測試：
  - 正常 CSV 輸入（兩列持倉）→ 回傳正確 PortfolioEntry dict
  - 含千分位（`"1,000"`）與負數（`"-75,000"`）的數字正確解析（`_parse_number` 單元測試）
  - 標題列（第一列）不進入 dict
  - 非數字代號列（`"小計"`, `""`）靜默略過
  - `httpx.RequestError` → 回傳 {}
  - HTTP 4xx（`HTTPStatusError`）→ 回傳 {}
  - `GOOGLE_SHEETS_ID` 為空（mock config）→ 回傳 {}，log warning

- [X] T005 [US1] 在 `src/fastapistock/services/stock_service.py` 新增：
  - `_merge_portfolio(stocks: list[RichStockData], portfolio: dict[str, PortfolioEntry]) -> list[RichStockData]`：
    純函式；對每支 stock 做 `portfolio.get(stock.symbol)`；
    有 entry → `stock.model_copy(update={'avg_cost': ..., 'unrealized_pnl': ..., 'shares': ...})`；
    無 entry → stock 不變；回傳新 list
  - 在 `get_rich_tw_stocks()` 末端呼叫（此時直接 import fetch_portfolio，不加快取）：
    ```python
    from fastapistock.repositories.portfolio_repo import fetch_portfolio
    portfolio = fetch_portfolio()
    return _merge_portfolio([results[code] for code in cleaned], portfolio)
    ```

- [X] T006 [P] [US1] 修改 `src/fastapistock/services/telegram_service.py` 的 `_format_rich_block()`，
  在漲跌行之後、美股盤前行之前插入持倉區塊（依 `contracts/portfolio-message-format.md`）：
  ```python
  if stock.avg_cost is not None and stock.shares is not None:
      pnl_pct = (stock.price - stock.avg_cost) / stock.avg_cost * 100 if stock.avg_cost else 0.0
      pnl_sign = '+' if pnl_pct >= 0 else ''
      pnl_pct_esc = _escape_md(f'{pnl_sign}{pnl_pct:.2f}')
      cost_esc = _escape_md(f'{stock.avg_cost:.2f}')
      lines.append('   ─── 持倉 ───')
      lines.append(f'   持股: `{stock.shares:,}`   成本: `{cost_esc}` \\({pnl_pct_esc}%\\)')
      if stock.unrealized_pnl is not None:
          pnl_abs_sign = '+' if stock.unrealized_pnl >= 0 else ''
          pnl_abs_esc = _escape_md(f'{pnl_abs_sign}{stock.unrealized_pnl:,.0f}')
          lines.append(f'   損益: `{pnl_abs_esc} TWD`')
  ```

- [X] T007 [P] [US1] 修改 `tests/test_telegram_formatter.py`，在 `_make_stock()` 新增
  `avg_cost`, `unrealized_pnl`, `shares` 可選參數（預設 None），並新增測試：
  - `avg_cost=820, shares=1000, unrealized_pnl=75000` → 訊息含「持倉」、「成本」、「損益」
  - `avg_cost=None` → 訊息不含「持倉」文字
  - `unrealized_pnl` 為負（`-35000`）→ 損益行含 `-` 且正確 escape
  - `market='US'` 且 `avg_cost` 有值 → 因 `market` 不限制持倉，但 avg_cost=None for US（由 service 保證），
    加測：`avg_cost=820, market='US'` 仍顯示持倉（formatter 不過濾，由 service 保證 US 為 None）

**Checkpoint**: `uv run pytest tests/test_portfolio_repo.py tests/test_telegram_formatter.py -v` 全部 PASS；
`curl "http://localhost:8000/api/v1/tgMessage/ID?stock=CODE"` 且 CODE 在試算表中 → Telegram 含持倉區塊

---

## Phase 4: US2 - 持倉快取避免重複請求（Priority: P2）

**Goal**: 持倉資料 Redis 快取（TTL=1 小時），快取命中時不重複抓取 Sheets；Redis 不可用時降級抓取

**Independent Test**: 短時間內觸發兩次推播，log 只出現一次「Fetching portfolio」，第二次為「Portfolio cache hit」

### Implementation: US2

- [X] T008 [US2] 在 `src/fastapistock/services/stock_service.py`：
  - 新增 `_PORTFOLIO_CACHE_KEY = 'portfolio:tw'`；import `PORTFOLIO_CACHE_TTL` from config
  - 新增 `_get_cached_portfolio() -> dict[str, PortfolioEntry]`：
    (1) `redis_cache.get(_PORTFOLIO_CACHE_KEY)` → 若命中，用 `cast(dict[str, object], raw)` 反序列化為 PortfolioEntry dict；
    (2) cache miss 或 Redis 不可用（get 回傳 None）→ 呼叫 `fetch_portfolio()`；
    (3) 若 portfolio 非空 → `redis_cache.put(_PORTFOLIO_CACHE_KEY, serialised, PORTFOLIO_CACHE_TTL)`；
    (4) return portfolio
  - 將 `get_rich_tw_stocks()` 中的 `fetch_portfolio()` 直接呼叫替換為 `_get_cached_portfolio()`

- [X] T009 [P] [US2] 建立 `tests/test_portfolio_cache.py`，使用 `fakeredis` mock `redis_cache`，測試：
  - 首次呼叫 `_get_cached_portfolio()` → 呼叫 `fetch_portfolio()` 一次，結果存入 Redis
  - 第二次呼叫 → 不呼叫 `fetch_portfolio()`，直接從 Redis 取
  - Redis 不可用（mock redis_cache.get 回傳 None）→ 呼叫 `fetch_portfolio()`，正常回傳（不崩潰）
  - TTL 過期（mock redis_cache.get 回傳 None）→ 重新 fetch

**Checkpoint**: `uv run pytest tests/test_portfolio_cache.py -v` 全部 PASS；
重複觸發推播，log 確認快取命中

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: 確保全部測試通過、程式碼品質達標

- [X] T010 [P] 執行 `uv run ruff check . --fix && uv run ruff format .`，修正所有 linting 問題
  （重點：`portfolio_repo.py` 的 import 順序、行長度、單引號；`stock_service.py` 的 cast import）

- [X] T011 [P] 執行 `uv run mypy src/`，修正型別錯誤
  （重點：`cast(dict[str, object], raw)` 反序列化；`PortfolioEntry` 欄位型別；`RichStockData` 新欄位）

- [X] T012 執行 `uv run pytest --cov=src --cov-report=term-missing`，
  確認 `portfolio_repo.py` 和 `stock_service.py` 新增程式碼覆蓋率 ≥ 80%；補充不足覆蓋的路徑

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup: config)
    ↓
Phase 2 (Foundational: schema)
    ↓
Phase 3 (US1: display)  ←── MVP 完成點
    ↓
Phase 4 (US2: cache)
    ↓
Phase 5 (Polish)
```

### US1 內部相依

```
T003 (portfolio_repo) ──→ T005 (service merge)
T004 [P]  ────────────────────────────────────→ [測試 T003]
T006 [P]  ← 依賴 T002 (schema)
T007 [P]  ← 依賴 T006
```

### US2 內部相依

```
T008 (cached portfolio) ← 依賴 T005 (merge) 的 fetch_portfolio import
T009 [P]                ← 依賴 T008
```

### 可平行執行組合

**Phase 3（US1 啟動後）**：
```
T003 → T005 → T006（循序）
T004 [P]（與 T003 同步，測試 repo）
T007 [P]（與 T006 同步，測試 formatter）
```

**Phase 5（Polish）**：
```
T010 [P]  T011 [P]  ← 同時執行
T012      ← 最後（需前兩項完成）
```

---

## Implementation Strategy

### MVP：只完成 US1（台股推播附帶持倉）

1. Phase 1: Setup（T001）
2. Phase 2: Foundational（T002）
3. Phase 3: US1（T003–T007）
4. **STOP & VALIDATE**：`curl /api/v1/tgMessage/ID?stock=2330`，Telegram 確認收到持倉區塊
5. 推上 Railway，驗證 `GOOGLE_SHEETS_ID` 設定正確

### Incremental Delivery

```
MVP（Phase 1–3）→ 持倉顯示上線，每次 push 都重抓試算表
  ↓
加 Phase 4（US2）→ Redis 快取，減少 Sheets 請求
  ↓
Phase 5 Polish → 品質保證
```

---

## Notes

- `_get_cached_portfolio()` 反序列化：`redis_cache.get()` 回傳 `dict[str, object]`，
  inner value 需 `cast(dict[str, object], raw)` 才能 index，mypy 才過
- `_parse_number()` 必須處理：空字串、純數字、千分位逗號（`1,000`）、負號（`-75,000`）
- `shares` 在 formatter 用 `f'{stock.shares:,}'` 加千分位，`,` 不需 escape（在 backtick 內）
- `pnl_pct_esc` 的 `+` 和 `.` 都需透過 `_escape_md()` escape（在括號外）
- `_merge_portfolio()` 為純函式，測試時直接傳入 mock portfolio dict，不需 mock Redis
- US2 (T009) 測試用 `unittest.mock.patch` mock `fastapistock.services.stock_service.redis_cache`，
  注入 fakeredis 或直接 mock get/put 行為
