# Tasks 019 — /history 圖表軸標籤、數值標籤與總覽圖上下分欄

依 `specs/019-history-chart-labels/spec.md` 實作。分支：`feat/019-history-chart-labels`
（**已存在且為目前 checkout**，見 T0）。只改 `chart_service.py` 與兩個測試檔。

---

## T0 確認 feature branch
- **目標**：工作在 `feat/019-history-chart-labels`，禁止直接改 main。
- **指令**：`git branch --show-current`；若不是該分支，
  `git checkout feat/019-history-chart-labels`（不存在才 `git checkout -b`）。
- **驗收**：`git branch --show-current` 輸出 `feat/019-history-chart-labels`；
  `git status` 無業務程式碼未提交變更（`.claude/settings.local.json`、`.vscode/` 為本機
  雜訊，不納入 commit）。

## T1 先改寫會失效的既有測試（red first）
- **目標**：把 twinx 語意的 QA 測試改為 stacked 子圖語意，並強化既有斷言，讓後續實作有
  明確的紅燈。
- **涉及檔案**：`tests/test_history_chart_qa.py`
- **要求**：
  - `test_all_market_dual_axes_currencies` → 更名
    `test_all_market_stacked_subplots_currencies`，斷言：
    `len(axes) == 2`、兩個 ylabel、`axes[0].get_position().y0 > axes[1].get_position().y0`、
    `axes[1].yaxis.get_ticks_position() == 'left'`、
    `axes[0].get_shared_x_axes().joined(axes[0], axes[1])`、
    `axes[0].get_xlabel() == ''`、`axes[1].get_xlabel() == 'Report period (monthly)'`
  - `test_us_single_market_axis_says_usd` / `test_tw_single_market_axis_says_twd`：
    加 `get_xlabel() == 'Report period (monthly)'` 與
    `axes[0].yaxis.get_major_formatter()(610000) == '610,000'`
  - `test_symbol_chart_legend_and_title`：加 `get_ylabel() == 'Price (TWD)'`、
    `get_xlabel() == 'Report period (monthly)'`
  - 更新 `TestSummaryAxisLabels` docstring 與區塊註解（移除 dual axes 字樣，標註 spec-019）
- **驗收（AC-1.1、AC-1.2、AC-1.3、AC-2.1、AC-4.1、AC-4.3）**：
  `uv run pytest tests/test_history_chart_qa.py -k "AxisLabels"` 此時**應失敗**
  （實作前）；其餘類別仍通過。

## T2 chart_service：軸標籤、格式器、格線（個股 + 單一市場總覽）
- **目標**：新增 `_price_ylabel`、`_thousands_formatter`、`_style_y_axis`，改
  `_style_x_axis(ax, report_type)`；套用到 `render_symbol_chart` 與單一市場
  `render_summary_chart`。
- **涉及檔案**：`src/fastapistock/services/chart_service.py`
- **要求**：
  - `from matplotlib.ticker import StrMethodFormatter`
  - 個股 `decimals=2`、總覽 `decimals=0`（常數 `_PRICE_DECIMALS` / `_PNL_DECIMALS`）
  - `ax.grid(True, axis='y', linestyle=':', alpha=0.4)`
  - xlabel `f'Report period ({report_type})'`，report_type 取 `ordered[0].report_type`
  - 未知 market → `'Price'`（E7）
- **驗收（AC-1.1、AC-1.2、AC-1.3、AC-2.1、AC-5.1、E7、E11）**：
  T1 強化的單一市場與個股測試轉綠；`uv run mypy src/` 零錯誤。

## T3 chart_service：數值標籤 + pnl 文字框
- **目標**：新增 `_label_points`（每點 / 僅末點，NaN 跳過）與 `_annotate_pnl_box`
  （axes fraction `(0.98, 0.95)`、`ha='right'`、`va='top'`、bbox 底色），刪除
  `_annotate_last_pnl`。
- **涉及檔案**：`src/fastapistock/services/chart_service.py`
- **要求**：
  - 個股：每個非 NaN close 點標 `f'{v:,.2f}'`；avg_cost 非全 NaN 時只標末點
    （末點 NaN 則不標，E9）
  - 單一市場總覽：每個非 NaN 點標 `f'{v:,.0f}'`
  - 文字 `f'PnL {float(pnl_pct):+.2f}%'`；`pnl_pct is None` → 不畫；不再依賴末點 close
    是否 NaN（E5）
  - `ax.margins(x=0.08, y=0.15)` 給標籤留白（建議，不斷言）
  - 每函式 ≤ 50 行；`render_symbol_chart` 若逼近上限，抽 `_plot_symbol_lines` helper
- **驗收（AC-2.2、AC-2.3、AC-3.1、AC-3.2、E2–E6、E9、E12、E13）**：
  在 `tests/test_chart_service.py` 新增 `TestSymbolChartLabels`（G1、G4、E3、E4、E5、E9）
  與 `TestSummaryChartLabels` 單一市場部分（G3、E12、E13）並通過；既有
  `test_last_pnl_pct_none_skips_annotation` 等仍通過。

## T4 chart_service：總覽 ALL 改為上下兩張 sharex 子圖
- **目標**：新增 `_plot_pnl_series` 與 `_render_stacked_summary`，刪除 `_plot_dual_axis`；
  `render_summary_chart` 在 `market == 'ALL'` 時使用 `_FIGSIZE_STACKED = (8.0, 6.5)`。
- **涉及檔案**：`src/fastapistock/services/chart_service.py`
- **要求**：
  - `ax_tw = fig.add_subplot(211)`；`ax_us = fig.add_subplot(212, sharex=ax_tw)`
    （**禁止 `fig.subplots`**，其 overload 回 `Any`）
  - `ax_tw.set_title(f'Account P&L ({report_type})')`；`ax_us` 無標題
  - 各自 `set_ylabel` + `legend` + 數值標籤 + `_style_y_axis(decimals=0)`
  - `ax_tw.tick_params(labelbottom=False)`；只對 `ax_us` 呼叫 `_style_x_axis`
  - 單一市場路徑共用 `_plot_pnl_series`，行為與 T2/T3 一致
  - 更新 `render_summary_chart` docstring 與 module docstring（spec-019）
- **驗收（AC-4.1–AC-4.5、E2 ALL、E14）**：
  T1 的 `test_all_market_stacked_subplots_currencies` 轉綠；
  `tests/test_chart_service.py::TestSummaryChartLabels` 補 G2 完整斷言
  （尺寸、位置、ticks_position、joined、title、xlabel、上圖刻度隱藏、legend、texts、格線）
  並通過；`TestRepeatedChartClicks` byte-identical 仍通過。

## T5 全量驗證 + commit + handoff-dev.json
- **目標**：品質門檻全過並產出 handoff。
- **指令**：
  1. `uv run ruff check . --fix && uv run ruff format .`
  2. `uv run mypy src/`
  3. `uv run pytest`（覆蓋率 ≥ 80%；`chart_service.py` 目標 100% 行覆蓋）
  4. `uv run pre-commit run --all-files`
  5. Conventional Commit，例：
     `fix: label /history chart axes and values, stack ALL summary subplots`
  6. 產出 `specs/019-history-chart-labels/handoff-dev.json`
     （`from: developer`、`to: qa`、`status: ready`、`changed_files` 完整列出、
     `ac_ref: specs/019-history-chart-labels/tasks.md`）
- **驗收**：四項指令零錯誤；commit 在 feature branch；不 merge、不 push、不 deploy；
  告知 orchestrator spawn **codex-reviewer**（非直接 QA）。

---

## AC 對照表

| AC / Edge | 驗證位置 |
|-----------|---------|
| AC-1.1 X 軸標題 | T1（強化既有）+ T2 |
| AC-1.2 Price 幣別 | T1 + T2 |
| AC-1.3 總覽幣別 | T1（既有斷言保留） |
| AC-2.1 千分位格式器 | T1 + T2 |
| AC-2.2 個股數值標籤 | T3 |
| AC-2.3 總覽數值標籤 | T3（單一市場）+ T4（ALL） |
| AC-3.1 / AC-3.2 pnl 文字框 | T3 |
| AC-4.1–4.5 stacked 子圖 | T1 + T4 |
| AC-5.1 格線 | T2 |
| AC-6.1 / 6.2 OO API、≤50 行、mypy | T2–T4，T5 驗證 |
| AC-6.3 byte-identical | T4（既有 QA 測試迴歸） |
| AC-6.4 簽名不變 | T5（test_history_webhook 迴歸） |
| E1 | 既有測試（不變） |
| E2、E3、E4、E5、E6、E9、E12、E13 | T3 |
| E7、E11 | T2 |
| E8、E10 | 既有 `TestExtremeValueRendering` 迴歸 + T3 可選補測 |
| E14 | T4 |
