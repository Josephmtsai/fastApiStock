# Implementation Plan: Google Sheets 持倉整合

**Branch**: `001-portfolio-sheets` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-portfolio-sheets/spec.md`

## Summary

在現有台股 Telegram 推播訊息中整合個人持倉資料。透過 Google Sheets CSV 匯出端點（公開
分享，無需認證）讀取持倉資訊，在 `get_rich_tw_stocks()` service 層合併後，
格式化為 Telegram MarkdownV2「持倉」區塊附加於每支股票之後。持倉資料以 Redis 快取
（TTL=1 小時），降級時（Sheets 不可達）靜默略過，不影響技術指標推播。

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: httpx（既有）、csv（stdlib）、redis-py（既有）
**New Dependencies**: 無（零新套件）
**Storage**: Redis（快取，key=`portfolio:tw`，TTL=PORTFOLIO_CACHE_TTL）
**Testing**: pytest + fakeredis + unittest.mock（mock httpx.get）
**Target Platform**: Railway（與主服務同 process）
**Performance Goals**: 快取命中 < 5 ms；cache miss（Sheets fetch）< 10 s
**Constraints**: httpx timeout=10 s；Sheets CSV 公開存取；Redis 不可用時降級
**Scale/Scope**: 單一用戶，3–5 支台股持倉

## Constitution Check

### 初始評估（Phase 0 前）

| 原則 | 狀態 | 說明 |
|------|------|------|
| I. Code Quality | ✅ PASS | 所有設定由 env var 讀取；型別標記完整；函式 < 50 行；無 print() |
| II. Testing | ✅ PASS | CSV 解析、merge、formatter 均有單元測試；mock httpx.get |
| III. API Consistency | ✅ PASS | 無新 API endpoint；現有 envelope 不變 |
| IV. Performance & Resilience | ✅ PASS | Redis cache + httpx timeout；Redis 不可用時 fetch live |
| V. Observability | ✅ PASS | portfolio fetch/cache hit/miss 均 log；middleware 覆蓋 API 路徑 |

**Security**: 試算表 ID 與 GID 由 env 讀取；系統唯讀，不寫入試算表

**無 Constitution 違規。**

## Project Structure

### Documentation (this feature)

```text
specs/001-portfolio-sheets/
├── plan.md                              # 本文件
├── spec.md                              # 功能規格
├── research.md                          # Phase 0 研究結論
├── data-model.md                        # Phase 1 資料模型
├── quickstart.md                        # 快速上手指南
├── contracts/
│   ├── env-variables.md                 # 環境變數合約
│   └── portfolio-message-format.md      # Telegram 持倉區塊格式規範
└── tasks.md                             # Phase 2（/speckit.tasks 產生）
```

### Source Code

```text
src/fastapistock/
├── config.py                # 修改：新增 GOOGLE_SHEETS_ID, GOOGLE_SHEETS_PORTFOLIO_GID,
│                            #        PORTFOLIO_CACHE_TTL
├── schemas/
│   └── stock.py             # 修改：RichStockData 新增 avg_cost, unrealized_pnl, shares（可選）
├── repositories/
│   └── portfolio_repo.py    # 新增：PortfolioEntry dataclass + fetch_portfolio()
├── services/
│   ├── stock_service.py     # 修改：新增 _get_cached_portfolio(), _merge_portfolio(),
│   │                        #        get_rich_tw_stocks() 末端呼叫 merge
│   └── telegram_service.py  # 修改：_format_rich_block() 新增持倉區塊
└── ...（其他不動）

tests/
├── test_portfolio_repo.py      # 新增：CSV 解析、數字格式、降級行為
├── test_telegram_formatter.py  # 修改：新增持倉顯示、隱藏、美股不顯示測試
└── ...（現有測試不動）
```

### 共用 Service 呼叫關係

```
手動 API                        定時排程
GET /api/v1/tgMessage           _scheduled_push()
        │                            │
        ▼                            ▼
  get_rich_tw_stocks()         get_rich_tw_stocks()  ← 同一函式
        │
        ├── yfinance fetch / Redis cache
        ├── _get_cached_portfolio()   ← Google Sheets CSV / Redis cache
        └── _merge_portfolio()        ← 合併持倉欄位
        │
        ▼
  send_rich_stock_message()
  _format_rich_block()  → 若有 avg_cost 則顯示持倉區塊
```

## Phase 1: Setup（設定層）

**Purpose**: 新增環境變數設定，無業務邏輯

- [ ] T001 在 `src/fastapistock/config.py` 新增三個設定項：
  - `GOOGLE_SHEETS_ID: str = os.getenv('GOOGLE_SHEETS_ID', '')`
  - `GOOGLE_SHEETS_PORTFOLIO_GID: str = os.getenv('GOOGLE_SHEETS_PORTFOLIO_GID', '')`
  - `PORTFOLIO_CACHE_TTL: int = int(os.getenv('PORTFOLIO_CACHE_TTL', '3600'))`

**Checkpoint**: `uv run python -c "from fastapistock.config import PORTFOLIO_CACHE_TTL; print(PORTFOLIO_CACHE_TTL)"` 印出 3600

---

## Phase 2: Schema 擴充

**Purpose**: 為 `RichStockData` 新增三個可選持倉欄位，向後相容

- [ ] T002 在 `src/fastapistock/schemas/stock.py` 的 `RichStockData` 新增欄位（docstring 同步更新）：
  ```python
  avg_cost: float | None = None
  unrealized_pnl: float | None = None
  shares: int | None = None
  ```

**Checkpoint**: `uv run python -c "from fastapistock.schemas.stock import RichStockData; r = RichStockData(symbol='0050', display_name='x', market='TW', price=100, prev_close=99, change=1, change_pct=1.01, ma20=98, volume=1000, volume_avg20=800); print(r.avg_cost)"` 印出 None

---

## Phase 3: Portfolio Repository

**Purpose**: 讀取 Google Sheets CSV，解析為 `PortfolioEntry` dict

- [ ] T003 建立 `src/fastapistock/repositories/portfolio_repo.py`：
  - `PortfolioEntry` frozen dataclass（symbol, shares, avg_cost, unrealized_pnl）
  - `_parse_number(raw: str) -> float`：strip 空白、移除逗號、轉 float
  - `fetch_portfolio() -> dict[str, PortfolioEntry]`：
    - 若 env var 未設 → log warning → return {}
    - httpx.get(CSV export URL, timeout=10, follow_redirects=True)
    - HTTP 錯誤 → log error → return {}
    - 解析 CSV，略過第一列（標題），略過非數字代號列
    - 解析 A（symbol）, C（shares）, F（avg_cost）, I（unrealized_pnl）

- [ ] T004 建立 `tests/test_portfolio_repo.py`，測試：
  - 正常 CSV 輸入 → 回傳正確 PortfolioEntry dict
  - 含千分位（`1,000`）與負數（`-75,000`）正確解析
  - 標題列正確略過（第一列不進 dict）
  - 非數字代號（小計列）靜默略過
  - httpx 拋出 RequestError → 回傳 {}
  - HTTP 4xx → 回傳 {}
  - env var 未設 → 回傳 {}（mock config）

**Checkpoint**: `uv run pytest tests/test_portfolio_repo.py -v` 全部 PASS

---

## Phase 4: Service 層整合

**Purpose**: 快取 Portfolio，合併至 RichStockData

- [ ] T005 在 `src/fastapistock/services/stock_service.py` 新增：
  - `_PORTFOLIO_CACHE_KEY = 'portfolio:tw'`
  - `_get_cached_portfolio() -> dict[str, PortfolioEntry]`：
    - redis_cache.get → 若命中，反序列化為 PortfolioEntry dict
    - 若 miss，呼叫 fetch_portfolio()，redis_cache.put(TTL=PORTFOLIO_CACHE_TTL)
    - Redis 不可用時（redis_cache.get 回傳 None）直接 fetch
  - `_merge_portfolio(stocks, portfolio) -> list[RichStockData]`：
    - 純函式；對每支 stock 查找 portfolio.get(stock.symbol)
    - 有 entry → `stock.model_copy(update={avg_cost, unrealized_pnl, shares})`
    - 無 entry → stock 不變

- [ ] T006 修改 `get_rich_tw_stocks()` 末端：
  ```python
  stocks = [results[code] for code in cleaned]
  portfolio = _get_cached_portfolio()
  return _merge_portfolio(stocks, portfolio)
  ```

**Checkpoint**: 呼叫 `get_rich_tw_stocks(['2330'])` 時（mock fetch_portfolio 回傳含 2330 的 dict），回傳的 RichStockData.avg_cost 不為 None

---

## Phase 5: Telegram Formatter

**Purpose**: 在訊息中顯示持倉區塊

- [ ] T007 修改 `src/fastapistock/services/telegram_service.py` 的 `_format_rich_block()`：
  在漲跌行之後、RSI 行之前插入（依 contracts/portfolio-message-format.md）：
  ```python
  if stock.avg_cost is not None and stock.shares is not None:
      pnl_pct = (stock.price - stock.avg_cost) / stock.avg_cost * 100 ...
      lines.append('   ─── 持倉 ───')
      lines.append(f'   持股: `{stock.shares:,}`   成本: `{cost_esc}` \\({pnl_pct_esc}%\\)')
      if stock.unrealized_pnl is not None:
          lines.append(f'   損益: `{pnl_abs_esc} TWD`')
  ```
  - 美股（`stock.market == 'US'`）不顯示持倉區塊（條件已由 avg_cost=None 自然滿足）

- [ ] T008 修改 `tests/test_telegram_formatter.py`，新增測試：
  - 有 avg_cost 時，訊息含「持倉」與「成本」文字
  - avg_cost 為 None 時，訊息不含「持倉」文字
  - unrealized_pnl 為負時，損益行正確顯示負號（escape 驗證）
  - market='US' 且 avg_cost 有值時，不顯示持倉區塊

**Checkpoint**: `uv run pytest tests/test_telegram_formatter.py -v` 全部 PASS

---

## Phase 6: Polish

- [ ] T009 [P] `uv run ruff check . --fix && uv run ruff format .`
- [ ] T010 [P] `uv run mypy src/`，確認 `cast(dict[str, object], raw)` 型別正確
- [ ] T011 `uv run pytest --cov=src --cov-report=term-missing`，確認覆蓋率 ≥ 80%（新增程式碼）

---

## Dependencies & Execution Order

```
Phase 1 (Setup / config)
    ↓
Phase 2 (Schema)
    ↓
Phase 3 (Repo + Tests)  ← T003, T004 可平行
    ↓
Phase 4 (Service)       ← T005, T006 循序（T005 → T006）
    ↓
Phase 5 (Formatter)     ← T007, T008 可平行
    ↓
Phase 6 (Polish)        ← T009, T010 可平行，T011 最後
```

## Notes

- `_get_cached_portfolio()` 中反序列化 Redis 值時需 `cast(dict[str, object], raw)`，因 `redis_cache.get()` 回傳 `dict[str, object] | None`
- 千分位逗號數字（`1,000`）在 `_parse_number()` 中統一處理，formatter 的 `_escape_md()` 會 escape 逗號內的 `.` 符號
- `shares` 為 `int`，在 formatter 用 `f'{stock.shares:,}'` 加千分位
- `_merge_portfolio()` 為純函式，不讀取外部狀態，易於單元測試（直接傳入 mock portfolio dict）
