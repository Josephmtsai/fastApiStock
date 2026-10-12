# Spec 020 — TW PnL `#N/A` Fallback (row-by-row recomputation)

## Overview

當台股 Google Sheet 總計格 I19 無法解析為數字（如 `#N/A`）時，`fetch_pnl_tw()` 改為逐列重算：
有數值 I 的持股列直接採用，I 非數值的持股列以即時報價重算 `shares × price − (D − E)`，
讓所有 `fetch_pnl_tw` 呼叫端（30 分鐘推播、收盤快照、`/pnl`、日報）不再顯示「unavailable」。

## Background / Root Cause

- `scheduler._send_daily_pnl_delta('TW')` → `portfolio_service.get_daily_pnl_delta_reply`
  → `portfolio_repo.fetch_pnl_tw()` → `_fetch_pnl_cell(gid, 18, 8, 'pnl:tw:<date>')`。
- I19 = `#N/A`，`_parse_number('#N/A')` 拋 `ValueError` → `_fetch_pnl_cell` 回傳 `None`
  （`portfolio_repo.py:271-275`）→ 訊息 `TW current PnL unavailable.`。
- 源頭：Sheet 0050 現價 (G) 的 GOOGLEFINANCE 失效 → H、I、I19 SUM 一路傳染 `#N/A`。

## User Stories

### US-1 TW PnL 在 Sheet 單一報價失效時仍可取得
As a 投資人, I want TW 未實現損益在 Sheet 某檔現價為 `#N/A` 時仍能被算出,
so that 30 分鐘推播、收盤基準快照、`/pnl` 與日報不會因 Sheet 單格故障而全部失效。

- **AC1** Given I19 為 `#N/A`，持股列（shares > 0）的 I 皆為數值，
  When 呼叫 `fetch_pnl_tw()`，Then 回傳這些 I 的總和，且不呼叫任何即時報價。
- **AC2** Given I19 為 `#N/A`，持股列 0050（shares 149957, D 8339244, E 0）的 I 為 `#N/A`，
  其他持股列 I 為數值，且即時報價 0050 = 60.0，
  When 呼叫 `fetch_pnl_tw()`，Then 回傳 `其他列 I 總和 + 149957 × 60.0 − (8339244 − 0)`
  （Golden Sample G1 = `5792545.0`）。
- **AC3** Given 持股列 I 為數值但與 `H − (D − E)` 不一致（如 2330 差 100000），
  When fallback 執行，Then 一律採用 Sheet 的 I 值（不重算）。
- **AC4** Given shares == 0 的列（已出清，例：0056、5904、00687B）其 G/H/I 為 `#N/A` 或空白，
  When fallback 執行，Then 該列被忽略，不呼叫即時報價、不影響總和。
- **AC5** Given fallback 被觸發，When 執行，Then 以 WARNING 記錄一次，訊息含 I19 原始值與
  所有 I 非數值的持股代號（例 `['0050']`）。
- **AC6** Given 任一需要即時報價的代號取價失敗（拋例外、價格 ≤ 0 或 NaN），
  When fallback 執行，Then `fetch_pnl_tw()` 回傳 `None`，並以 WARNING 記錄失敗代號清單。
- **AC7** Given fallback 成功算出數值，When 回傳，Then **不寫入** `pnl:tw:<date>` 快取
  （`redis_cache.put` 不被呼叫）。
- **AC8** Given I19 為合法數值，When 呼叫 `fetch_pnl_tw()`，Then 行為與現況完全一致
  （回傳該值、寫入快取、不觸發 fallback、不呼叫即時報價）。

### US-2 既有行為不回歸
As a 維運者, I want US PnL 與其他失敗路徑行為維持不變, so that 修正不引入新風險。

- **AC9** `fetch_pnl_us()` 在 H21 為 `#N/A` 時仍回傳 `None`（無 fallback）。
- **AC10** 快取命中、設定缺失、HTTP/Request 錯誤、目標格超出範圍 → 行為與現況一致
  （快取命中回傳快取值；其餘回傳 `None`；超出範圍不觸發 fallback）。
- **AC11** Telegram 訊息格式（`format_market_daily_pnl_delta`、`_format_pnl_reply`、日報）不變；
  僅數值來源改變。

## Modules

| 檔案 | 異動 | 說明 |
|------|------|------|
| `src/fastapistock/repositories/portfolio_repo.py` | 修改 | 新增 fallback 相關私有函式；`_fetch_pnl_cell` 新增可選 `fallback` 參數；`fetch_pnl_tw` 傳入 fallback；修正 docstring（`I20` → `I19`） |
| `tests/test_portfolio_repo_pnl.py` | 修改（新增測試） | 新增 `TestFetchPnlTwFallback`、US `#N/A` 回歸測試；既有測試不改 |
| `src/fastapistock/services/stock_service.py` | 不動 | 透過 lazy import 呼叫其 `get_rich_tw_stock` |
| `src/fastapistock/services/portfolio_service.py` | 不動 | 自動受益 |
| `src/fastapistock/services/report_service.py` | 不動 | 自動受益（L363 `portfolio_repo.fetch_pnl_tw`） |
| `src/fastapistock/scheduler.py` | 不動 | 自動受益 |

### 決策 D1：fallback 放在 repository 層（`portfolio_repo`）
- 呼叫端有兩條路徑：`portfolio_service`（scheduler、/pnl、收盤快照）以及
  `report_service` **直接** 呼叫 `portfolio_repo.fetch_pnl_tw`。放在 repo 層可讓所有呼叫端
  自動受益、零呼叫端改動、既有 service 層測試（patch `fetch_pnl_tw`）全部不受影響。
- 放在 service 層則需改 `report_service` 呼叫點與其多個測試的 patch 目標，違反 KISS。

### 決策 D2：即時報價來源 = `stock_service.get_rich_tw_stock(code).price`，以函式內 lazy import 取得
- `stock_service` 在 module level `from fastapistock.repositories.portfolio_repo import ...`，
  若 `portfolio_repo` 在 module level import `stock_service` 會形成循環 import。
  函式內 lazy import 在呼叫時兩模組皆已載入，無循環問題；專案已有相同慣例
  （`scheduler.py:89`、`report_service.py:523`、`routers/webhook.py:208`）。
- `get_rich_tw_stock` 已具備：Redis 快取 `rich_tw:<code>:<date>`（TTL 300s，與 30 分鐘
  TW 個股推播共用同一快取鍵，推播後幾乎必然命中）+ `fetch_tw_rich_stock` 內的
  `SystemRandom().uniform(0.1, 0.5)` 隨機延遲 + yfinance timeout。符合台股「隨機延遲 + local cache」規範。
- `.price` 來自 `fast_info.last_price`（失敗時退回最近日 close），比 Sheet GOOGLEFINANCE 更即時，可接受。
- 不採 `twstock_repo.fetch_tw_rich_stock` 直呼：無快取，違反 local cache 規則。
- 不新增輕量取價函式：YAGNI，通常僅 1 檔需取價且多半快取命中。
- ruff 規則集為 `E,F,I,UP,S,B`，無 `PLC0415`，函式內 import 不會被 lint 擋下。

### 決策 D3：fallback 結果**不寫入** `pnl:tw:<date>` 快取
- `PORTFOLIO_CACHE_TTL` 預設 3600s。若快取 fallback 值，將 (a) 把含即時價的數值凍結 1 小時，
  30 分鐘推播會連續兩次顯示相同 Current；(b) Sheet 恢復後最長 1 小時仍讀到 fallback 值。
- 不快取的成本：每次呼叫多一次 Sheet CSV 下載（與 cache miss 相同成本，10s timeout）＋
  取價（`rich_tw` 300s 快取吸收）。呼叫頻率低（30 分鐘推播、收盤快照、/pnl、日報），成本可忽略。
- 一旦 Sheet 恢復，下一次呼叫即走正常路徑並寫入快取。
- 若當日稍早 I19 正常時已寫入快取，快取命中期間仍回傳該快取值（既有行為，不變）。

## Data Contracts

### 既有常數（不變）
`_COL_SYMBOL=0`, `_COL_SHARES=2`, `_COL_UNREALIZED_PNL=8`, `_TW_PNL_ROW=18`, `_TW_PNL_COL=8`。

### 新增常數
```python
_COL_BUY_TOTAL = 3   # D 買入總金額
_COL_SELL_TOTAL = 4  # E 賣出總金額
```

### 新增 / 修改函式簽名

```python
def _parse_optional_number(raw: str) -> float | None:
    """Parse a cell; return None for blank or non-numeric (e.g. '#N/A') values."""

def _fetch_tw_live_price(symbol: str) -> float | None:
    """Return a live TW price via stock_service.get_rich_tw_stock (lazy import).

    Returns None (and logs WARNING with symbol + exception) when the lookup raises
    any Exception, or when price is NaN / not finite / <= 0.
    """

def _recompute_tw_pnl(rows: list[list[str]], summary_raw: str) -> float | None:
    """Recompute TW total unrealized PnL row-by-row when the summary cell is invalid.

    Args:
        rows: Full parsed CSV rows of the TW sheet.
        summary_raw: Raw text of the summary cell (for logging only).

    Returns:
        Sum of per-holding unrealized PnL, or None when any needed value is
        unavailable or no holding row exists.
    """

def _fetch_pnl_cell(
    gid: str,
    row: int,
    col: int,
    cache_key: str,
    fallback: Callable[[list[list[str]], str], float | None] | None = None,
) -> float | None:
    """(existing) + when the target cell fails to parse and `fallback` is given,
    return fallback(rows, raw_cell) WITHOUT writing to cache."""
```

`fetch_pnl_tw()` 公開簽名不變 `() -> float | None`；內部改為
`_fetch_pnl_cell(gid, _TW_PNL_ROW, _TW_PNL_COL, cache_key, fallback=_recompute_tw_pnl)`。
`fetch_pnl_us()` 不傳 fallback，行為不變。`Callable` 由 `collections.abc` import。

若 `_fetch_pnl_cell` 因新增分支超過 50 行，Developer 可抽出 `_download_csv_rows(gid) -> list[list[str]] | None`
（HTTP 下載 + csv 解析 + 錯誤 log），不改變對外行為與 log 文字。

### `_recompute_tw_pnl` 演算法

1. 掃描持股區 `rows[1:_TW_PNL_ROW]`（跳過表頭 row 0，排除總計列 row 18 及其後）。
2. 每列：`symbol = row[0].strip()`；若 `symbol == ''` 或 `len(row) <= _COL_SHARES` → 跳過
   （涵蓋 row 17 `Unrealize` 標籤列與空白列）。**不使用** `isdigit()` 過濾，以涵蓋 `00687B` 類英數代號。
3. `shares = _parse_optional_number(row[2])`：
   - 空白 → 視為 0 → 跳過。
   - 非空白但非數值（如 `#N/A`）→ 記入 `failed`（原因：shares unparseable）。
   - `<= 0` → 跳過（已出清）。
4. `pnl = _parse_optional_number(row[8])`（`len(row) <= 8` 視為 None）：
   - 數值 → 累加（**即使與 H−(D−E) 不一致也採用**）。
   - None（空白或 `#N/A` 等）→ 記入 `na_symbols`，進入重算：
     - `buy = _parse_optional_number(D)`, `sell = _parse_optional_number(E)`，空白視為 0.0，
       非數值 → 記入 `failed`。
     - `price = _fetch_tw_live_price(symbol)`；None → 記入 `failed`。
     - 成功 → 累加 `shares * price - (buy - sell)`。
5. 開始重算前（掃描完 na_symbols 後或於函式開頭）以 WARNING 記錄 fallback 使用（見 Golden G3）。
   實作上可先完整掃描再 log，順序不強制，但 **fallback WARNING 只 log 一次**。
6. 若 `failed` 非空 → WARNING 列出失敗代號 → 回傳 `None`。
7. 若未找到任何 shares > 0 的持股列 → WARNING → 回傳 `None`。
8. 否則回傳 `float` 總和（不四捨五入）。

即時報價僅對 `na_symbols` 依序呼叫（通常 1 檔），不平行化。

## API Design

無新增或修改路由。

## Golden Sample

### Fixture CSV（測試用，對齊 2026-10-12 live snapshot；省略列以 shares=0 填充）

19 列（row 0..18），10 欄 A..J：
```
row 0 : 代號,股名,持有股數,買入總金額,賣出總金額,平均成本,現價,市值,未實現損益,已實現損益
row 1 : 0050,元大台灣50,149957,8339244,0,55.61090179,#N/A,#N/A,#N/A,
row 2 : 0056,元大高股息,0,330026,333918,,58.6,,,3892
row 3 : 2330,台積電,3345,4646352,373462,1389.043946,2550,8529750,4156860,
row 4 : (filler) 9901,X,0,0,0,,,,,
row 5 : (filler) 9902,X,0,0,0,,,,,
row 6 : (filler) 9903,X,0,0,0,,,,,
row 7 : 2317,鴻海,1150,157671,0,137.1052174,245,281750,124079,
row 8 : (filler) 9904,X,0,0,0,,,,,
row 9 : (filler) 9905,X,0,0,0,,,,,
row 10: 5904,寶雅,0,197600,198800,,#N/A,,,1200
row 11: 006208,富邦台50,5000,651550,110000,130.31,263.25,1316250,774700,
row 12: (filler) 9906,X,0,0,0,,,,,
row 13: 00687B,國泰20年美債,0,52180,55460,,#N/A,,,3280
row 14: 009816,X,5000,54821,0,10.9642,16.92,84600,29779,
row 15: 0052,富邦科技,2000,107321,0,53.6605,66.95,133900,26579,
row 16: 2454,聯發科,35,139678,0,3990.8,4630,162050,22372,
row 17: ,,,,,,,Unrealize,SUM,
row 18: ,,,,,,,,#N/A,75125
```
（股名欄內容不影響計算；含逗號的值需以 csv quoting 或避免使用逗號。）

### G1 — fallback 成功（AC2/AC3/AC4/AC7）
- mock `fastapistock.services.stock_service.get_rich_tw_stock` → 回傳 `price=60.0` 的物件
  （可用 `MagicMock(price=60.0)`）。
- 數值 I 合計：4156860 + 124079 + 774700 + 29779 + 26579 + 22372 = **5134369**
- 0050 重算：149957 × 60.0 − (8339244 − 0) = 8997420 − 8339244 = **658176**
- 預期 `fetch_pnl_tw()` == **5792545.0**（`pytest.approx`）
- `get_rich_tw_stock` 恰被呼叫 1 次，引數 `'0050'`。
- 2330 採 Sheet I（4156860），非 H−(D−E)=4256860。
- `redis_cache.put` 未被呼叫。

### G2 — 取價失敗（AC6）
- `get_rich_tw_stock` 拋 `StockNotFoundError`（或任意 `Exception`）→ `fetch_pnl_tw()` is `None`；
  WARNING 記錄含 `0050`；`redis_cache.put` 未被呼叫。

### G3 — Log 內容（AC5/AC6，用 `caplog` 驗證，level WARNING，logger `fastapistock.repositories.portfolio_repo`）
- fallback 啟動（建議文字，關鍵字必含 `fallback` 與代號）：
  `TW PnL summary cell unparseable ('#N/A'); using row-by-row fallback, N/A symbols: ['0050']`
- 取價失敗：
  `TW live price unavailable for 0050: <exception>`（由 `_fetch_tw_live_price`）
- 失敗彙總：
  `TW PnL fallback failed; unavailable symbols: ['0050']`
- QA 以「訊息含 `fallback` 且含 `0050`」比對，不要求逐字。
- 原有 `logger.error('Failed to parse PnL cell value: ...')` 在有 fallback 時改為不輸出 ERROR
  或保留皆可；**US 路徑（無 fallback）必須保留 ERROR log**。

### G4 — Telegram 訊息（AC11，不變）
fallback 成功後 30 分鐘推播文字（plain text，無 MarkdownV2，格式沿用 `format_market_daily_pnl_delta`）：
```
TW PnL vs previous close

Current: +5,792,545 TWD
Previous close: +<baseline> TWD
Change: <sign><delta> TWD
```

## Edge Cases

| # | 情境 | 處理 |
|---|------|------|
| E1 | I19 合法數值 | 現行路徑；寫快取；不呼叫 fallback/取價（AC8） |
| E2 | I19 = `#N/A`，所有持股列 I 為數值 | 回傳 I 加總；不取價；不寫快取（AC1/AC7） |
| E3 | I19 = `#N/A`，某持股列 I = `#N/A` | 取即時價重算該列（AC2） |
| E4 | 持股列 I 數值但 ≠ H−(D−E) | 採 Sheet I（AC3） |
| E5 | shares == 0 或空白的列（G/H/I 為 `#N/A`/空白） | 忽略，不取價（AC4） |
| E6 | 取價拋例外（StockNotFoundError、網路錯誤等） | 捕捉 `Exception`、WARNING，記入 failed → 回傳 None（AC6）；不得向上拋 |
| E7 | 取價回傳 NaN / inf / ≤ 0 | 視為失敗（AC6） |
| E8 | 多檔 I 為 `#N/A`，其中一檔取價失敗 | 回傳 None；WARNING 列出所有失敗代號（AC6） |
| E9 | 需重算列的 D 或 E 為非數值 | 記入 failed → None |
| E10 | 持股列 shares 為非空白非數值（如 `#N/A`） | 記入 failed → None（無法判斷是否持有） |
| E11 | 持股區無任何 shares > 0 的列 | WARNING → None（避免以 0 污染收盤基準） |
| E12 | 英數代號（如 `00687B`）shares > 0 且 I 非數值 | 照常取價 `get_rich_tw_stock('00687B')`（yfinance `.TW` 後綴）；若上櫃代號查無資料 → E6 → None |
| E13 | 目標格超出範圍（row/col） | 維持現行：ERROR + None，不觸發 fallback（AC10） |
| E14 | HTTP/Request 錯誤、設定缺失 | 維持現行 None（AC10） |
| E15 | `pnl:tw:<date>` 快取命中 | 維持現行回傳快取值（AC10） |
| E16 | I19 為空白字串 | 維持現行：`_parse_number('')` = 0.0，不觸發 fallback（不擴充需求） |
| E17 | US H21 = `#N/A` | 維持現行 None，無 fallback（AC9） |
| E18 | Redis 不可用 | `get_rich_tw_stock` 內 `redis_cache.get/put` 既有容錯；若仍拋例外則落入 E6 |
| E19 | row 長度 < 9（I 欄缺） | I 視為 None → 走重算 |

## Affected Tests

### 盤點方式
`Grep tests/` 關鍵字：`fetch_pnl_tw`、`_fetch_pnl_cell`、`portfolio_repo`、`#N/A`。

### 必壞（Must break）
**無。** 理由：
- `tests/test_portfolio_repo_pnl.py`：
  - `_make_csv_rows()` 的 row 18 col 8 = `'1234567'`（合法數值）→ 不觸發 fallback。
  - `test_returns_cached_float_on_cache_hit`、`test_fetches_live_on_cache_miss_and_caches_result`
    （`mock_cache.put.assert_called_once()` 仍成立，E1）、`test_returns_none_on_http_error`、
    `test_returns_none_when_config_missing`、`test_returns_none_when_row_out_of_range`（E13 不觸發 fallback）
    → 全數維持通過。
  - `TestFetchPnlUs` 4 個測試 → US 無 fallback，不變。
- 沒有任何既有測試以 `#N/A` 斷言 TW 回傳 `None`（Grep `#N/A` in tests/ 無結果）。
- `_fetch_pnl_cell` 新增參數有預設值 `None`，既有呼叫相容；無測試直接呼叫 `_fetch_pnl_cell`。

### 不受影響（patch 在 service 層或回傳值已 mock）
- `tests/test_portfolio_service.py`（L112、L139 monkeypatch `portfolio_service.fetch_pnl_tw`）
- `tests/test_pnl_service.py`（L608/634/663 mock `fetch_pnl_tw.return_value`）
- `tests/test_report_service.py`（L89）、`tests/test_report_pipeline.py`（L72）、
  `tests/test_report_pipeline_integration.py`（L43）、`tests/test_spec005_edge_cases.py`（L577/678/697）
  —— 皆 patch `report_service.portfolio_repo.fetch_pnl_tw`。
- `tests/test_portfolio_repo.py`（`_parse_number`、`fetch_portfolio`）—— 兩者不改。
- `tests/test_portfolio_cache.py`（`stock_service._get_cached_portfolio`）—— 不改。
- scheduler 相關測試 —— mock `portfolio_service`，不改。

### 需新增（`tests/test_portfolio_repo_pnl.py` 新 class `TestFetchPnlTwFallback`）
patch 目標：`fastapistock.repositories.portfolio_repo.redis_cache` / `.config` / `.httpx.get`，
以及取價 `fastapistock.services.stock_service.get_rich_tw_stock`（lazy import 於呼叫時解析屬性，
patch 原始模組即可）。

| 測試 | AC/E |
|------|------|
| `test_fallback_sums_numeric_rows_without_price_lookup`（0050 I 改為數值、I19 `#N/A`） | AC1, E2 |
| `test_fallback_recomputes_na_row_with_live_price`（Golden G1 = 5792545.0，呼叫 1 次 `'0050'`） | AC2, AC3, AC4, E3, E4, E5 |
| `test_fallback_result_not_cached` | AC7 |
| `test_fallback_logs_warning_with_na_symbols`（caplog） | AC5 |
| `test_fallback_returns_none_when_price_lookup_raises`（caplog 含 `0050`） | AC6, E6 |
| `test_fallback_returns_none_when_price_non_positive_or_nan`（parametrize 0.0、-1.0、nan） | E7 |
| `test_fallback_returns_none_when_any_of_multiple_fails` | E8 |
| `test_fallback_returns_none_when_buy_total_unparseable` | E9 |
| `test_fallback_returns_none_when_shares_unparseable` | E10 |
| `test_fallback_returns_none_when_no_holdings` | E11 |
| `test_fallback_includes_alphanumeric_symbol`（00687B shares>0、I `#N/A`） | E12 |
| `test_valid_summary_does_not_call_price_lookup`（I19 數值 → `get_rich_tw_stock` 未呼叫） | AC8, E1 |
| `TestFetchPnlUs::test_returns_none_when_summary_is_na`（H21 `#N/A` → None，不取價） | AC9, E17 |
| `_parse_optional_number` 單元測試（`'#N/A'`→None、`''`→None、`'1,234'`→1234.0、`'-5'`→-5.0） | 支援 |

## Out of Scope

- 台股假日曆（10/9 補假造成 baseline 日期錯誤）。
- Sheet 端 GOOGLEFINANCE / SUM 公式修正。
- `fetch_pnl_us` / US Sheet 的 fallback。
- 上櫃（`.TWO`）代號取價支援。
- 對 `_parse_number` 空白 → 0.0 語意的任何修改。
- Telegram 訊息格式、`fetch_portfolio` 的 `isdigit` 過濾規則（per-stock 推播合併邏輯）。
- 對 memory 中 0050 現價低估（9/20）情境的 code guard（Sheet 給出數值但錯誤的價格，非本 spec 範圍）。
