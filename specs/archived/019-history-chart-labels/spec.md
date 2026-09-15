# Spec 019 — /history 圖表軸標籤、數值標籤與總覽圖上下分欄

## Overview
修正 `/history` 圖表「看不出 X/Y 軸意義與實際數值」的問題：補 X 軸標題、Y 軸幣別、
千分位刻度、每點數值標籤、pnl% 註解移入圖內、總覽 ALL 圖由 twinx 雙軸改為上下兩張
sharex 子圖、加 Y 軸淡色格線。**只改 `chart_service.py` 與測試**，`history_handler`
呼叫介面（`render_symbol_chart(rows)` / `render_summary_chart(rows, market=...)`）不動。

## 程式碼探索摘要（Developer 必讀）

| 項目 | 現況（`src/fastapistock/services/chart_service.py`） |
|------|------|
| 個股圖 | L31–63 `render_symbol_chart`：`set_ylabel('Price')`、無 xlabel、`_annotate_last_pnl` 以 offset points 掛在末點（會被裁切） |
| 總覽圖 | L66–107 `render_summary_chart`；ALL 走 L110–126 `_plot_dual_axis`（`ax.twinx()`） |
| 共用 | `_to_float_series`（None→NaN）、`_style_x_axis`（只旋轉 45°）、`_fig_to_png`（tight_layout + Agg） |
| 呼叫端 | `history_handler.py` L487–538 `_send_symbol_chart` / `_send_summary_chart`，rows 上限 `_DEFAULT_RECORDS_LIMIT = 12`（L57） |
| 文字結果數值格式 | `history_handler._format_decimal` 一律 `{value:,.2f}`（L642） |
| matplotlib | 3.11.0（`uv.lock` L1282），自帶 type stubs |
| mypy | `mypy.ini` `strict = True`、`warn_unused_ignores = False`；`Any` 禁用（CLAUDE.md） |

**型別已驗證（matplotlib 3.11 stubs）**：
- `Axes.annotate(text, xy: tuple[Any, Any], ...)` — x 為 period 字串可通過 mypy（既有程式已如此使用）。
- `Figure.add_subplot(pos: int, **kwargs) -> Axes` — `fig.add_subplot(212, sharex=ax_top)` 回傳型別明確。
- **`Figure.subplots(...)` 預設 `squeeze=True` 且 nrows≠1 時 overload 回 `Any`，禁止使用**；一律用 `add_subplot`。
- `matplotlib.ticker.StrMethodFormatter(fmt: str)`；`Formatter.__call__(x: float, pos: int | None = None) -> str` 可在測試直接呼叫驗證格式。
- `Axes.grid(visible, which, axis, **kwargs)`、`Axes.tick_params(axis, **kwargs)`、`Axes.margins(x=, y=)` 皆有型別。

## User Stories

### US-1 看得懂軸的意義
As a 投資人, I want to 圖表的 X 軸與 Y 軸都有標題並註明單位（期別／幣別）,
so that 我不用猜軸代表什麼。

- AC-1.1（X 軸標題）
  - Given 任一 `/history` 圖表（個股或總覽，weekly 或 monthly）
  - When 圖表渲染完成
  - Then 帶 X 刻度的 Axes 其 `ax.get_xlabel()` 為 `'Report period (weekly)'` 或
    `'Report period (monthly)'`（依 `rows[0].report_type`）
- AC-1.2（個股 Y 軸幣別）
  - Given 個股圖，`rows[0].market` 為 `'TW'` / `'US'`
  - When 圖表渲染完成
  - Then `ax.get_ylabel()` 為 `'Price (TWD)'` / `'Price (USD)'`
- AC-1.3（總覽 Y 軸幣別，既有行為保留）
  - Given 總覽圖 market `'TW'` / `'US'`
  - Then 單一 Axes `get_ylabel()` 為 `'TW P&L (TWD)'` / `'US P&L (USD)'`（與 spec-018 相同）

### US-2 讀得出實際數值
As a 投資人, I want to 每個資料點上方直接標出數值、刻度有千分位,
so that 我不用對照文字訊息才知道那一點是多少。

- AC-2.1（千分位刻度）
  - Given 任一圖表的任一 Axes
  - When 取 `ax.yaxis.get_major_formatter()`
  - Then 為 `StrMethodFormatter`；個股圖 `fmt == '{x:,.2f}'`（`formatter(1234.5) == '1,234.50'`），
    總覽圖 `fmt == '{x:,.0f}'`（`formatter(610000) == '610,000'`）
- AC-2.2（個股圖數值標籤）
  - Given 個股圖 N 筆 rows（N ≤ 12），close 皆非 NaN
  - When 圖表渲染完成
  - Then `ax.texts` 中含 N 個 close 標籤（`f'{close:,.2f}'`），若 avg_cost 末點非 NaN 則
    另含 1 個 avg cost 標籤（`f'{avg_cost[-1]:,.2f}'`）；NaN 點不產生標籤
- AC-2.3（總覽圖數值標籤）
  - Given 總覽圖 N 期（N ≤ 12）
  - When 圖表渲染完成
  - Then 每條 P&L 線所在 Axes 的 `ax.texts` 含 N 個 `f'{value:,.0f}'` 標籤
    （負數以 `-` 開頭，如 `'-12,345'`；不加 `+`）；NaN 點不產生標籤

### US-3 pnl% 註解不被裁切
As a 投資人, I want to 個股圖的報酬率註解完整顯示在圖內,
so that 我不會看到被切掉一半的數字。

- AC-3.1
  - Given 個股圖，末筆 `pnl_pct` 非 None
  - When 圖表渲染完成
  - Then `ax.texts` 含一個文字 `f'PnL {pnl_pct:+.2f}%'` 的 Text，其
    `get_transform() == ax.transAxes`、`get_ha() == 'right'`、`get_va() == 'top'`、
    `get_bbox_patch() is not None`（有底色文字框），座標 `(0.98, 0.95)`（axes fraction），
    故永遠落在 Axes 內、不受資料範圍影響
- AC-3.2
  - Given 末筆 `pnl_pct` 為 None
  - Then `ax.texts` 中無任何以 `'PnL '` 開頭的文字（spec-018 E4 行為保留）

### US-4 總覽 ALL 圖可對應線與刻度
As a 投資人, I want to TW 與 US 損益各自一張子圖、各自的刻度,
so that 我不必猜左右軸哪個對應哪條線。

- AC-4.1（上下兩子圖）
  - Given `render_summary_chart(rows, market='ALL')`
  - When 圖表渲染完成
  - Then `fig.axes` 恰 2 個；`axes[0]` 為 TW（上）、`axes[1]` 為 US（下），
    `axes[0].get_position().y0 > axes[1].get_position().y0`；
    `axes[1].yaxis.get_ticks_position() == 'left'`（非 twinx 右軸）；
    `axes[0].get_shared_x_axes().joined(axes[0], axes[1]) is True`
- AC-4.2（各自標籤）
  - Then `axes[0].get_ylabel() == 'TW P&L (TWD)'`、`axes[1].get_ylabel() == 'US P&L (USD)'`；
    `axes[0].get_title() == 'Account P&L (monthly)'`（或 weekly）、`axes[1].get_title() == ''`；
    `axes[0].get_legend()` 與 `axes[1].get_legend()` 皆非 None，各含一個 label
- AC-4.3（共用 X 軸只在下方標示）
  - Then `axes[1].get_xlabel() == 'Report period (monthly)'`、`axes[0].get_xlabel() == ''`；
    `axes[0]` 的 X 刻度文字隱藏（`all(not t.get_visible() for t in axes[0].get_xticklabels())`）
- AC-4.4（圖高）
  - Then `tuple(fig.get_size_inches()) == (8.0, 6.5)`；單一市場與個股圖維持 `(8.0, 4.5)`
- AC-4.5（單一市場不變）
  - Given market `'TW'` / `'US'`
  - Then `fig.axes` 恰 1 個（既有 QA 測試 `len(axes) == 1` 仍成立）

### US-5 格線輔助讀值
As a 投資人, I want to Y 軸有淡色水平格線, so that 我能把點對到刻度。

- AC-5.1
  - Given 任一圖表的任一資料 Axes
  - Then `ax.yaxis.get_gridlines()[0].get_visible() is True` 且
    `ax.xaxis.get_gridlines()[0].get_visible() is False`（僅水平格線）；
    格線樣式 `linestyle=':'`、`alpha=0.4`（樣式不強制斷言）

### US-6 工程約束（不回歸）
- AC-6.1 只用 OO API（`Figure` + `FigureCanvasAgg`），**不 import pyplot**；所有標籤 ASCII。
- AC-6.2 每個函式 ≤ 50 行；`uv run mypy src/` 零錯誤、無 `Any`；Ruff 單引號、88 字元。
- AC-6.3 相同輸入 → byte-identical PNG（既有 `TestRepeatedChartClicks` 斷言必須繼續成立）。
- AC-6.4 `render_symbol_chart` / `render_summary_chart` 簽名與 `ValueError` 行為不變。

## Modules

| Module | 職責 | 涉及檔案 | 異動類型 |
|--------|------|---------|---------|
| chart_service | 軸標籤、格式器、數值標籤、pnl 文字框、stacked 子圖 | `src/fastapistock/services/chart_service.py` | **修改** |
| chart_service 單元測試 | 新增 Figure/Axes 結構斷言 | `tests/test_chart_service.py` | **修改**（新增測試類） |
| QA 補測 | 改寫 twinx 測試、強化既有斷言 | `tests/test_history_chart_qa.py` | **修改** |
| history_handler | 呼叫端 | `src/fastapistock/services/history_handler.py` | **不動** |
| telegram_service / webhook / repo | — | — | **不動** |
| 依賴 | matplotlib 3.11 已具備 `ticker.StrMethodFormatter` | `pyproject.toml` / `uv.lock` | **不動** |

## Data Contracts

### 公開函式（簽名不變）

```python
def render_symbol_chart(rows: list[SymbolSnapshot]) -> bytes: ...
def render_summary_chart(
    summaries: list[ReportSummary], *, market: str = 'ALL'
) -> bytes: ...
```
Docstring 需更新：`render_summary_chart` 的 `'ALL'` 描述改為「上下兩張 sharex 子圖」，
移除 dual y-axis 字句；module docstring 補一句 spec-019。

### 模組常數（新增／調整）

```python
_FIGSIZE = (8.0, 4.5)            # 既有：個股圖、單一市場總覽
_FIGSIZE_STACKED = (8.0, 6.5)    # 新增：ALL 上下兩子圖
_DPI = 100                       # 既有
_PRICE_DECIMALS = 2              # 個股價格：與 history_handler._format_decimal 一致
_PNL_DECIMALS = 0                # P&L 金額：刻度與標籤皆整數千分位
_LABEL_FONTSIZE = 8              # 數值標籤字級
_CURRENCY_BY_MARKET = {'TW': 'TWD', 'US': 'USD'}
```

### 私有 helper（建議拆分，維持每函式 ≤ 50 行）

```python
def _price_ylabel(market: str) -> str:
    """'Price (TWD)' / 'Price (USD)'; unknown market -> 'Price' (E7)."""

def _thousands_formatter(decimals: int) -> StrMethodFormatter:
    """StrMethodFormatter(f'{{x:,.{decimals}f}}')."""

def _style_y_axis(ax: Axes, *, decimals: int) -> None:
    """Apply thousands formatter + faint horizontal grid (axis='y', ls=':', alpha=0.4)."""

def _style_x_axis(ax: Axes, report_type: str) -> None:
    """set_xlabel(f'Report period ({report_type})') + 45-degree tick rotation."""

def _label_points(
    ax: Axes,
    periods: list[str],
    values: list[float],
    *,
    decimals: int,
    only_last: bool = False,
) -> None:
    """Annotate each non-NaN point (or only the last one) with f'{v:,.{decimals}f}'.

    ax.annotate(text, xy=(period, value), xytext=(0, 6),
                textcoords='offset points', ha='center', va='bottom',
                fontsize=_LABEL_FONTSIZE)
    only_last=True: label index -1 only, skipped when values[-1] is NaN.
    """

def _annotate_pnl_box(ax: Axes, pnl_pct: Decimal | None) -> None:
    """Replace _annotate_last_pnl. No-op when pnl_pct is None.

    ax.text(0.98, 0.95, f'PnL {float(pnl_pct):+.2f}%', transform=ax.transAxes,
            ha='right', va='top', fontsize=9,
            bbox={'boxstyle': 'round', 'facecolor': 'white', 'alpha': 0.8})
    """

def _plot_pnl_series(
    ax: Axes,
    periods: list[str],
    values: list[float],
    *,
    label: str,
) -> None:
    """One P&L line: plot(marker='o') + set_ylabel(label) + legend + labels + y style."""

def _render_stacked_summary(
    fig: Figure,
    periods: list[str],
    tw: list[float],
    us: list[float],
    report_type: str,
) -> None:
    """ALL layout: ax_tw = fig.add_subplot(211); ax_us = fig.add_subplot(212, sharex=ax_tw).

    ax_tw.set_title(f'Account P&L ({report_type})'); ax_tw.tick_params(labelbottom=False)
    _plot_pnl_series(ax_tw, ..., label='TW P&L (TWD)'); _plot_pnl_series(ax_us, ..., label='US P&L (USD)')
    _style_x_axis(ax_us, report_type)   # xlabel + rotation only on the bottom axes
    """
```
`_plot_dual_axis` **刪除**；`_annotate_last_pnl` **刪除**（由 `_annotate_pnl_box` 取代）。

### 個股圖組裝順序（決定 `ax.texts` 順序，測試以集合/Counter 比對而非依賴順序）
1. `ax.plot(periods, close, marker='o', linestyle='-', label='close')`
2. 若 avg_cost 非全 NaN：`ax.plot(periods, avg_cost, marker='o', linestyle='--', label='avg cost')`
3. `_label_points(ax, periods, close, decimals=_PRICE_DECIMALS)`
4. 若 avg_cost 非全 NaN：`_label_points(ax, periods, avg_cost, decimals=_PRICE_DECIMALS, only_last=True)`
5. `_annotate_pnl_box(ax, ordered[-1].pnl_pct)`
6. `set_title`（不變）、`ax.set_ylabel(_price_ylabel(first.market))`、`ax.legend()`
7. `_style_y_axis(ax, decimals=_PRICE_DECIMALS)`、`_style_x_axis(ax, first.report_type)`
8. 建議 `ax.margins(x=0.08, y=0.15)` 讓末點標籤與頂部文字框有空間（不斷言）

## API Design
無新增 HTTP 路由；Telegram callback grammar 不變。

## Golden Sample（供 QA 以 Figure/Axes 物件比對；擷取方式同 `TestSummaryAxisLabels._capture_figure`：monkeypatch `chart_service._fig_to_png` 為 spy）

### G1 個股圖 — 輸入 `tests/test_chart_service.py::_snapshot` 兩筆（2026-02、2026-03；price 800、cost 700、pnl_pct 14.29、TW、monthly）

| 元素 | 斷言 |
|------|------|
| Axes 數 | `len(fig.axes) == 1` |
| 尺寸 | `tuple(fig.get_size_inches()) == (8.0, 4.5)` |
| 標題 | `ax.get_title() == '2330 (TW) monthly'` |
| X 軸標題 | `ax.get_xlabel() == 'Report period (monthly)'` |
| Y 軸標題 | `ax.get_ylabel() == 'Price (TWD)'` |
| Legend | `[t.get_text() for t in ax.get_legend().get_texts()] == ['close', 'avg cost']` |
| Y 格式器 | `isinstance(fmt, StrMethodFormatter)`；`fmt(1234.5) == '1,234.50'` |
| 數值標籤 | `Counter(t.get_text() for t in ax.texts) == Counter({'800.00': 2, '700.00': 1, 'PnL +14.29%': 1})` |
| pnl 文字框 | 該 Text：`get_transform() == ax.transAxes`、`get_ha() == 'right'`、`get_va() == 'top'`、`get_bbox_patch() is not None` |
| 格線 | `ax.yaxis.get_gridlines()[0].get_visible()` True；`ax.xaxis.get_gridlines()[0].get_visible()` False |
| 線數 | `len(ax.get_lines()) == 2` |

### G2 總覽 ALL — 輸入 `_summary` 兩筆（2026-02、2026-03；tw 500000、us 8000、monthly）

| 元素 | 斷言 |
|------|------|
| Axes 數 | `len(fig.axes) == 2` |
| 尺寸 | `tuple(fig.get_size_inches()) == (8.0, 6.5)` |
| 上下排列 | `axes[0].get_position().y0 > axes[1].get_position().y0` |
| 非 twinx | `axes[1].yaxis.get_ticks_position() == 'left'` |
| sharex | `axes[0].get_shared_x_axes().joined(axes[0], axes[1])` |
| 標題 | `axes[0].get_title() == 'Account P&L (monthly)'`；`axes[1].get_title() == ''` |
| Y 軸 | `axes[0].get_ylabel() == 'TW P&L (TWD)'`；`axes[1].get_ylabel() == 'US P&L (USD)'` |
| X 軸 | `axes[0].get_xlabel() == ''`；`axes[1].get_xlabel() == 'Report period (monthly)'` |
| 上圖 X 刻度隱藏 | `all(not t.get_visible() for t in axes[0].get_xticklabels())` |
| Legend | 各 Axes 一個 legend，label 分別 `['TW P&L (TWD)']`、`['US P&L (USD)']` |
| Y 格式器 | 兩軸 `fmt(610000) == '610,000'` |
| 數值標籤 | `[t.get_text() for t in axes[0].texts] == ['500,000', '500,000']`；`axes[1]` 為 `['8,000', '8,000']` |
| 格線 | 兩軸 Y 格線可見、X 格線不可見 |
| 線數 | 各 Axes `len(ax.get_lines()) == 1` |

### G3 總覽單一市場 TW — `_summary` 一筆（2026-03）
`len(fig.axes) == 1`、`(8.0, 4.5)`、ylabel `'TW P&L (TWD)'`、xlabel `'Report period (monthly)'`、
title `'Account P&L (monthly)'`、texts `['500,000']`、legend `['TW P&L (TWD)']`。

### G4 weekly
任一圖以 `report_type='weekly'` 的 rows 渲染 → xlabel `'Report period (weekly)'`；
個股 title `'2330 (TW) weekly'`；總覽 title `'Account P&L (weekly)'`。

## Edge Cases

| # | 情境 | 處理 |
|---|------|------|
| E1 | rows / summaries 為空 | `ValueError`（不變） |
| E2 | 單一資料點 | 1 個數值標籤 + marker 可見；ALL 兩子圖各 1 標籤 |
| E3 | avg_cost 全為 NaN（runtime None） | 不畫虛線、**不產生 avg cost 標籤**；legend 僅 `['close']` |
| E4 | 末筆 `pnl_pct` 為 None | 無 `PnL ...` 文字框，其餘照常 |
| E5 | 末點 close 為 NaN 但 `pnl_pct` 非 None | 文字框**仍顯示**（改掛 axes fraction，不再依賴末點座標）；該點不產生數值標籤 |
| E6 | 序列中間有 NaN | 該點跳過標籤，線段中斷（不變） |
| E7 | `rows[0].market` 非 TW/US | ylabel 退回 `'Price'`（無幣別），不 raise |
| E8 | 極端值（`999999999999.99`、`-0.01`） | 格式器輸出 `'999,999,999,999'` / `'-0'`（`,.0f` 四捨五入）；標籤可能重疊，可接受，不拋錯 |
| E9 | avg_cost 末點 NaN 但前面有值 | `only_last=True` 只看末點 → 不標（不回溯前一個非 NaN 點） |
| E10 | 12 點（`_DEFAULT_RECORDS_LIMIT`） | 12 個標籤、fontsize 8；接受視覺擁擠 |
| E11 | `report_type` 非 weekly/monthly | 直接內插原字串 `Report period (<raw>)`，不驗證（DB 已約束） |
| E12 | 負 P&L | 標籤 `'-12,345'`；刻度同格式；不加 `+` |
| E13 | 全 0 序列（既有 QA 測試） | 標籤 `'0'` × N，正常出圖 |
| E14 | 決定論 | 無隨機、無時間戳 → 相同輸入 byte-identical（AC-6.3） |

## Affected Tests

### `tests/test_history_chart_qa.py`

| 測試 | 影響 | 動作 |
|------|------|------|
| `TestSummaryAxisLabels::test_all_market_dual_axes_currencies` | **不會變紅但語意失效**：`len(axes) == 2` 與兩個 ylabel 在「兩張子圖」下仍成立，無法區分 twinx 與 stacked | **改寫**：更名 `test_all_market_stacked_subplots_currencies`，加 AC-4.1/4.3 斷言（`get_position().y0` 上>下、`yaxis.get_ticks_position() == 'left'`、`joined(...)`、`axes[0].get_xlabel() == ''`、`axes[1].get_xlabel() == 'Report period (monthly)'`）；更新該類 docstring 與區塊註解（移除「dual axes」字樣） |
| `::test_us_single_market_axis_says_usd` / `::test_tw_single_market_axis_says_twd` | 通過（ylabel 不變、仍 1 個 Axes） | **強化**：加 `get_xlabel()`、格式器 `fmt(610000) == '610,000'` |
| `::test_symbol_chart_legend_and_title` | 通過（legend 與 title 不變） | **強化**：加 `get_ylabel() == 'Price (TWD)'`、`get_xlabel()` |
| `TestRepeatedChartClicks`（byte-identical × 5） | 通過（渲染仍決定論） | 迴歸驗證（AC-6.3） |
| `TestExtremeValueRendering` | 通過（僅 PNG magic） | 迴歸驗證 E8/E13 |
| `TestCaptionSafety` / `TestChartStepGuards` / Toggle / Reset | 不受影響（不碰 chart 內部） | 迴歸驗證 |

### `tests/test_chart_service.py`
| 測試 | 影響 | 動作 |
|------|------|------|
| `TestRenderSymbolChart` / `TestRenderSummaryChart` 全部 | 通過（僅 PNG magic 與 ValueError） | 不改；**新增** `TestSymbolChartLabels`、`TestSummaryChartLabels` 類（Figure 擷取 spy 方式同 QA 檔，可在檔內建 fixture），覆蓋 G1–G4、E2–E7、E9、E12 |

### `tests/test_history_webhook.py`
`render_symbol_chart` / `render_summary_chart` 均被 `patch` 取代（L58–63），**不受影響**。

### 其餘（test_history_api、test_report_history_repo 等）
不受影響；T-final 全量 pytest 迴歸。

## Out of Scope
- 修改 `history_handler.py`（caption、callback grammar、rows 上限）
- 中文標籤 / 字型安裝 / Dockerfile
- pyplot、`matplotlib.use()`、pixel 比對測試
- 數值標籤防重疊演算法（adjustText 等）
- 個股圖 unrealized_pnl 金額標籤（只標價格與 pnl%）
- 每點 pnl% 標籤（僅末筆一個文字框）
