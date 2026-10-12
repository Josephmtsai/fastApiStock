# Tasks — 020-tw-pnl-na-fallback

Spec: `specs/020-tw-pnl-na-fallback/spec.md`
Branch: `feature/020-tw-pnl-na-fallback`

## T0 — 建立 feature branch
- 目標：自最新 `main` 建立 `feature/020-tw-pnl-na-fallback`。
- 指令：`git checkout main && git checkout -b feature/020-tw-pnl-na-fallback`
- 驗收：`git branch --show-current` 顯示新分支；工作區既有未追蹤檔（`.vscode/`、
  `.claude/settings.local.json`）不得被 commit。

## T1 — 新增解析輔助與常數
- 檔案：`src/fastapistock/repositories/portfolio_repo.py`
- 內容：
  - 常數 `_COL_BUY_TOTAL = 3`、`_COL_SELL_TOTAL = 4`。
  - `_parse_optional_number(raw: str) -> float | None`（空白/非數值 → None；處理千分位逗號、負數）。
  - Google Style docstring、完整型別。
- 驗收：單元測試 `'#N/A'`→None、`''`→None、`'  '`→None、`'1,234'`→1234.0、`'-5'`→-5.0。
- 對應：支援 AC1–AC6。

## T2 — 即時報價 helper
- 檔案：`portfolio_repo.py`
- 內容：`_fetch_tw_live_price(symbol: str) -> float | None`
  - 函式內 lazy import：`from fastapistock.services.stock_service import get_rich_tw_stock`
    （module level import 會循環；加一行註解說明原因）。
  - `except Exception as exc` → `logger.warning('TW live price unavailable for %s: %s', symbol, exc)` → None。
  - `price` 非 finite 或 `<= 0` → WARNING → None。
- 驗收：E6、E7 測試通過；module 可被單獨 import（`python -c "import fastapistock.repositories.portfolio_repo"`）無循環錯誤。
- 對應：AC6, E6, E7, E18。

## T3 — 逐列重算 `_recompute_tw_pnl`
- 檔案：`portfolio_repo.py`
- 內容：依 spec「`_recompute_tw_pnl` 演算法」實作 `_recompute_tw_pnl(rows, summary_raw) -> float | None`。
  - 掃描 `rows[1:_TW_PNL_ROW]`；symbol 空白跳過；不使用 `isdigit()`。
  - shares 空白/≤0 跳過；非數值 → failed。
  - I 數值 → 採用；否則 D/E + 即時價重算。
  - fallback WARNING 只 log 一次（含 summary_raw 與 N/A 代號清單）。
  - failed 非空 → WARNING + None；無持股 → WARNING + None。
  - 函式 ≤ 50 行；必要時拆出單列處理 helper。
- 驗收：AC1–AC6、E2–E12、E19。

## T4 — 接入 `_fetch_pnl_cell` / `fetch_pnl_tw`
- 檔案：`portfolio_repo.py`
- 內容：
  - `_fetch_pnl_cell` 新增 `fallback: Callable[[list[list[str]], str], float | None] | None = None`
    （`from collections.abc import Callable`）。
  - parse `ValueError` 時：`fallback is None` → 維持原 ERROR log + None；
    否則 `return fallback(rows, rows[row][col])`，**不寫快取**。
  - 超出範圍分支不呼叫 fallback。
  - `fetch_pnl_tw` 傳入 `fallback=_recompute_tw_pnl`；docstring 修正 `I20` → `I19` 並描述 fallback 與不快取行為。
  - `fetch_pnl_us` 不改。
  - 若 `_fetch_pnl_cell` 超過 50 行，抽出 `_download_csv_rows(gid)`，log 文字不變。
- 驗收：AC7、AC8、AC9、AC10；既有 `tests/test_portfolio_repo_pnl.py` 9 個測試不修改即通過。

## T5 — 測試
- 檔案：`tests/test_portfolio_repo_pnl.py`
- 內容：依 spec「Affected Tests → 需新增」表格新增 `TestFetchPnlTwFallback`、
  `TestFetchPnlUs::test_returns_none_when_summary_is_na`、`_parse_optional_number` 單元測試。
  - Fixture CSV 依 Golden Sample（19 列）以 `csv.writer` 產生，避免逗號問題。
  - 取價 patch：`patch('fastapistock.services.stock_service.get_rich_tw_stock', ...)`。
  - G1 斷言 `pytest.approx(5792545.0)`，`assert_called_once_with('0050')`，`mock_cache.put.assert_not_called()`。
  - log 斷言用 `caplog`（level WARNING），比對含 `fallback` 與 `0050`。
- 驗收：全部新測試通過；`portfolio_repo.py` 覆蓋率 ≥ 80%。
- 對應：AC1–AC10, E1–E19（E13–E15 由既有測試覆蓋）。

## T6 — 全量驗證 + Commit + handoff-dev.json
- 指令：
  - `uv run ruff check . --fix && uv run ruff format .`
  - `uv run mypy src/`
  - `uv run pytest --cov=fastapistock --cov-report=term-missing`
  - `uv run pre-commit run --all-files`
- Commit（Conventional）：`fix(portfolio): fall back to row-by-row TW PnL when I19 is #N/A`
  （可拆為 `fix:` + `test:` 兩個 commit）。
- 產出 `specs/020-tw-pnl-na-fallback/handoff-dev.json`（from developer → qa，changed_files 完整列出，
  ac_ref 指向本檔），告知 orchestrator spawn **codex-reviewer**。
- 驗收：所有指令綠燈；AC11（訊息格式未變）透過既有 `test_pnl_service.py` / `test_portfolio_service.py` 全數通過確認。

## AC 對照表

| AC / Edge | 說明 | Task | 測試 |
|-----------|------|------|------|
| AC1 / E2 | 全數值列加總、不取價 | T3, T5 | `test_fallback_sums_numeric_rows_without_price_lookup` |
| AC2 / E3 | `#N/A` 列以即時價重算（G1 = 5792545.0） | T2, T3, T5 | `test_fallback_recomputes_na_row_with_live_price` |
| AC3 / E4 | 採 Sheet I，不重算 | T3, T5 | 同上（2330） |
| AC4 / E5 | shares==0 忽略 | T3, T5 | 同上（0056/5904/00687B，呼叫次數 1） |
| AC5 | fallback WARNING 含代號 | T3, T5 | `test_fallback_logs_warning_with_na_symbols` |
| AC6 / E6 / E8 | 取價失敗 → None + WARNING | T2, T3, T5 | `..._price_lookup_raises`, `..._any_of_multiple_fails` |
| E7 | 價格 NaN / ≤0 | T2, T5 | `..._price_non_positive_or_nan` |
| AC7 | fallback 不寫快取 | T4, T5 | `test_fallback_result_not_cached` |
| AC8 / E1 | 正常路徑不變、不取價 | T4, T5 | 既有 `test_fetches_live_on_cache_miss_and_caches_result` + `test_valid_summary_does_not_call_price_lookup` |
| AC9 / E17 | US `#N/A` → None | T4, T5 | `TestFetchPnlUs::test_returns_none_when_summary_is_na` |
| AC10 / E13–E15 | 快取命中/設定缺失/HTTP/超範圍不變 | T4 | 既有 `TestFetchPnlTw` 測試 |
| E9 | D/E 非數值 | T3, T5 | `..._buy_total_unparseable` |
| E10 | shares 非數值 | T3, T5 | `..._shares_unparseable` |
| E11 | 無持股 → None | T3, T5 | `..._no_holdings` |
| E12 | 英數代號納入 | T3, T5 | `test_fallback_includes_alphanumeric_symbol` |
| E16 | I19 空白維持 0.0 | — | 不新增（行為不變） |
| E18 | Redis 不可用 | T2 | 由 E6 涵蓋 |
| E19 | row 長度 < 9 | T3 | 可併入 E12 或獨立測試（選配） |
| AC11 | 訊息格式不變 | T6 | 既有 service 測試全綠 |
