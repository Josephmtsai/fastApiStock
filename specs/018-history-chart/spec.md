# Spec 018 — /history 查詢結果圖表化與結果頁快速按鈕

## Overview
在 `/history` 互動選單的兩種結果頁(個股序列、帳戶總覽)底部加入快速按鈕列
(圖表 / 週月切換 / 重新選擇),點「圖表」以 matplotlib(Agg)渲染 PNG 並以
sendPhoto 新訊息傳送;原文字結果訊息保留不動。

## User Stories

### US-1 個股走勢圖
As a 投資人, I want to 在個股歷史查詢結果按「圖表」看到收盤價與平均成本走勢圖,
so that 我不用逐行讀數字就能看出成本與價格的相對位置。

- AC-1.1
  - Given 個股結果頁(由 `hist:p:symbol:TW:2330:monthly` 渲染)已顯示且底部有按鈕列
  - When 使用者點「📈 圖表」(callback `hist:g:symbol:TW:2330:monthly`)
  - Then bot 以 sendPhoto 傳送**新訊息** PNG:收盤價實線 + 平均成本虛線 +
    最後一點標註 pnl%,caption 註明 symbol/market/週期;原文字訊息不變
- AC-1.2
  - Given 該 symbol/period 組合查無資料
  - When 使用者點「📈 圖表」
  - Then bot 以文字回覆「查無資料,無法產生圖表」,不送圖,webhook 回 200

### US-2 帳戶總覽圖
As a 投資人, I want to 在帳戶總覽結果按「圖表」看到 TW/US 未實現損益趨勢線,
so that 我能快速掌握兩市場損益走向。

- AC-2.1
  - Given 總覽結果頁(`hist:p:summary:ALL:monthly`)已顯示
  - When 使用者點「📈 圖表」(callback `hist:g:summary:ALL:monthly`)
  - Then bot 傳送新 PNG:TW 損益線(左 y 軸,標示 TWD)+ US 損益線(右 y 軸,
    標示 USD),雙 y 軸明確區分幣別
- AC-2.2
  - Given 使用者先前選擇單一市場(如 TW)
  - When 點「📈 圖表」(callback `hist:g:summary:TW:monthly`)
  - Then 圖表只畫該市場一條線、單 y 軸並標示對應幣別

### US-3 週月一鍵切換
As a 投資人, I want to 在結果頁直接切換週報/月報,
so that 我不用重新走完整選單流程。

- AC-3.1
  - Given 月報結果頁(`hist:p:symbol:TW:2330:monthly` 渲染後)
  - When 使用者點「📅 切換週報」(callback `hist:p:symbol:TW:2330:weekly`)
  - Then 同一則訊息被 editMessageText 重渲染為週報結果,底部按鈕列同步更新
    (圖表按鈕帶 weekly、切換按鈕改為「切換月報」)

### US-4 重新選擇
As a 投資人, I want to 在結果頁一鍵回到第一層選單,
so that 我能立即查另一檔股票或另一種報表。

- AC-4.1
  - Given 任一結果頁
  - When 使用者點「🔄 重新選擇」(callback `hist:r:menu`)
  - Then 同一則訊息被 edit 為第一層 type menu(帳戶總覽 / 個股查詢),
    keyboard 與 `_send_type_menu` 相同

### US-5 文字捷徑一致性
As a 投資人, I want to `/history 2330` 的文字結果也帶相同按鈕列,
so that 兩種入口體驗一致。

- AC-5.1
  - Given 使用者輸入 `/history 2330` 且 TW 有資料
  - When bot 回覆文字結果
  - Then 回覆訊息附上按鈕列(圖表 / 切換週報 / 重新選擇),market 取自
    `rows[0].market`、period 為 `monthly`;**不自動附圖**,文字內容不變

## Modules

| Module | 職責 | 涉及檔案 | 異動類型 |
|--------|------|---------|---------|
| chart_service | Decimal→float、Figure 組裝、PNG bytes 輸出(Agg,無 GUI) | `src/fastapistock/services/chart_service.py` | 新增 |
| telegram_service | `send_photo` multipart 上傳,錯誤處理比照 `reply_to_chat` | `src/fastapistock/services/telegram_service.py` | 修改(僅新增函式) |
| history_handler | g/r step 分派、結果頁按鈕列、文字捷徑按鈕、docstring grammar 更新 | `src/fastapistock/services/history_handler.py` | 修改 |
| pyproject | `matplotlib` 依賴 | `pyproject.toml` / `uv.lock` | 修改 |
| webhook | callback 分發 | `src/fastapistock/routers/webhook.py` | **不動**(prefix 不變) |
| Dockerfile | 部署 | `Dockerfile` | **不動**(matplotlib wheel 自帶 DejaVu 字型,ASCII 標籤足夠) |

## Data Contracts

### chart_service(新模組)

```python
def render_symbol_chart(rows: list[SymbolSnapshot]) -> bytes:
    """Render close-price (solid) vs avg-cost (dashed) chart as PNG bytes.

    Raises:
        ValueError: when rows is empty.
    """

def render_summary_chart(
    summaries: list[ReportSummary],
    *,
    market: str = 'ALL',   # 'TW' | 'US' | 'ALL'
) -> bytes:
    """Render TW/US unrealized-PnL trend chart as PNG bytes.

    market='ALL': dual y-axis, TW line (left, TWD) + US line (right, USD).
    market='TW'|'US': single line, single axis with currency label.

    Raises:
        ValueError: when summaries is empty.
    """
```

**實作要求(Agg backend 且零 E402 風險)**:
- 使用 matplotlib **OO API**,禁止 import pyplot:
  ```python
  from matplotlib.backends.backend_agg import FigureCanvasAgg
  from matplotlib.figure import Figure
  ```
  `FigureCanvasAgg` 即 Agg backend,無 GUI、thread-safe、無全域狀態,
  module 頂部一般 import 即可,不需 `matplotlib.use()`、不觸發 E402。
  (驗證結論:若走 pyplot 路線,`matplotlib.use('Agg')` 之後的 module-level
  `import matplotlib.pyplot` **會**觸發 Ruff E402,故棄用該路線。)
- 輸出:`io.BytesIO()` + `canvas.print_png(buf)` / `fig.savefig(buf, format='png')`,
  回傳 `buf.getvalue()`。
- Decimal 一律轉 `float` 再繪圖;None 值該點跳過或線段中斷(見 Edge Cases)。
- 每條線加 `marker='o'`,確保單一資料點仍可見。
- 函式 ≤50 行:抽出 `_to_float_series()`、`_fig_to_png()` 等私有 helper。

**圖表標籤(一律 ASCII,禁止中文)**:

| 圖 | 元素 | 標籤 |
|----|------|------|
| symbol | 標題 | `{symbol} ({market}) {report_type}`(report_type 取自 rows[0]) |
| symbol | 實線 legend | `close` |
| symbol | 虛線 legend | `avg cost` |
| symbol | 末點標註 | `{pnl_pct:+.2f}%`(pnl_pct 為 None 則省略) |
| symbol | y 軸 | `Price` |
| summary | TW 線 legend / 左軸 | `TW P&L (TWD)` |
| summary | US 線 legend / 右軸 | `US P&L (USD)` |
| 共同 | x 軸 | `report_period` 原字串(YYYY-MM 或 YYYY-MM-DD),必要時旋轉 45 度 |

### telegram_service.send_photo(新函式)

```python
def send_photo(
    chat_id: int | str,
    photo: bytes,
    caption: str | None = None,
) -> bool:
    """POST /sendPhoto with multipart/form-data upload.

    data={'chat_id': ..., 'caption': ...(有值才帶)}
    files={'photo': ('chart.png', photo, 'image/png')}
    timeout=_REQUEST_TIMEOUT;無 TELEGRAM_TOKEN → log error + return False;
    HTTPStatusError / RequestError → log error + return False(不拋錯)。
    """
```

### Callback grammar(history_handler docstring 需同步更新)

```
hist:g:symbol:<market>:<symbol>:<period>   # send chart (new message)
hist:g:summary:<market|ALL>:<period>       # send summary chart
hist:r:menu                                # reset → first-layer type menu
```

長度驗證:最長 `hist:g:symbol:US:GOOGL:monthly` = 30 bytes < 64。
`hist:r` 只有 2 段會被 `handle_callback` 的 `len(parts) < 3` guard 擋下,
故 reset 一律用 3 段 `hist:r:menu`,不放寬既有 guard。

### 結果頁按鈕列(symbol flow,summary flow 同構)

```python
[
    [('📈 圖表', f'hist:g:symbol:{market}:{symbol}:{period}'),
     ('📅 切換週報' if period == 'monthly' else '📅 切換月報',
      f'hist:p:symbol:{market}:{symbol}:{opposite_period}')],
    [('🔄 重新選擇', 'hist:r:menu')],
]
```
summary flow:`hist:g:summary:{market_choice}:{period}` 與
`hist:p:summary:{market_choice}:{opposite}`。
按鈕列由新 helper `_result_keyboard_symbol(...)` / `_result_keyboard_summary(...)`
產生,`_render_symbol` / `_render_summary` 的 `edit_message_text` 加傳
`reply_markup`;文字捷徑 `handle_text_command` 的成功回覆同樣附上
(`reply_to_chat` 已支援 `reply_markup`)。

### handle_callback 分派新增

```python
elif step == 'g':
    _step_send_chart(chat_id, parts)      # 新訊息,不需 message_id
elif step == 'r':
    _step_reset(chat_id, message_id)      # edit 回 type menu
```

`_step_send_chart` 流程:驗證 parts(market/period 白名單同 p step,不合法
即 log + return)→ 查 repo(與 `_render_*` 相同參數)→ rows 空則
`reply_to_chat('查無資料,無法產生圖表')` → `render_*_chart` 包在
`try/except Exception`(matplotlib 例外型別不可列舉,須加註釋說明例外於此
邊界收斂)→ 失敗 `logger.exception` + `reply_to_chat('圖表產生失敗,請稍後再試')`
→ 成功 `send_photo(chat_id, png, caption)`;`send_photo` 回 False 時
`reply_to_chat('圖表傳送失敗,請稍後再試')`。全程不拋出,webhook 恆 200。

## API Design
無新增 HTTP 路由。webhook 既有 `POST /api/v1/webhook/telegram` 行為不變
(`_dispatch_callback` 僅檢查 `hist:` prefix,g/r step 自動流入
`history_handler.handle_callback`)。

## Golden 描述(圖表元素清單,非像素比對)
- symbol chart:1 條實線(close)+ 1 條虛線(avg cost)+ legend 兩項 +
  末點 pnl% annotation + 標題含 symbol/market/report_type + x 軸為 period 字串
- summary chart(ALL):左軸 TW 線 + 右軸 US 線,兩軸 label 含幣別
- 測試僅驗:回傳 bytes 以 `\x89PNG\r\n\x1a\n` 開頭、長度 > 0、函式不拋錯

## Edge Cases

| # | 情境 | 處理 |
|---|------|------|
| E1 | g step 查詢 rows 為空 | 文字回覆「查無資料,無法產生圖表」,不送圖,200 |
| E2 | 單一資料點 | marker='o' 確保可見,正常出圖 |
| E3 | avg_cost 全為 None(型別為 Decimal 但防禦 runtime None) | 略過虛線,只畫實線 |
| E4 | 末筆 pnl_pct 為 None | 省略 annotation,其餘正常 |
| E5 | summary 只有一期 | 兩條線各一點,正常出圖 |
| E6 | send_photo HTTP 失敗(回 False) | log + 文字回覆「圖表傳送失敗」,200 |
| E7 | 渲染拋例外 | except Exception + logger.exception + 文字回覆,200 |
| E8 | callback_data 長度 | 最長 30 bytes,已驗證 < 64 |
| E9 | g step 帶非法 market/period | 白名單驗證失敗 → log warning + 靜默 return |
| E10 | `hist:r`(2 段)或 `hist:g` 段數不足 | 既有 len guard / step 內 guard 擋下,log |
| E11 | Decimal 精度 | 統一 float() 轉換後繪圖,顯示誤差可接受 |
| E12 | TELEGRAM_TOKEN 未設 | send_photo 回 False,比照既有函式 |

## Affected Tests 盤點

| 測試 | 影響 | 動作 |
|------|------|------|
| `tests/test_history_webhook.py::TestCallbackQueryFlow::test_period_summary_renders_results` | **必壞**:L280 斷言 `'reply_markup' not in kwargs` | 改為斷言 reply_markup 存在且含 `hist:g:summary:TW:monthly`、toggle、`hist:r:menu` |
| `::test_period_symbol_renders_results` | 不壞(未斷言 markup) | 增補按鈕列斷言 |
| `TestHistoryTextCommand::test_symbol_only_auto_detects_market` / `test_us_prefix_calls_repo_with_us` | 不壞(僅讀 `args[1]`) | 增補 reply_markup 斷言(AC-5.1) |
| 其餘 test_history_webhook / test_history_api / test_report_history_repo | 不受影響 | 迴歸驗證 |
| 新增 `tests/test_chart_service.py` | — | PNG magic、空 rows raise ValueError、E2–E5 |
| 新增 send_photo 測試(併入 telegram 測試檔或新檔) | — | multipart payload、E6/E12、HTTPStatusError/RequestError 回 False |
| 新增 g/r step webhook 測試(併入 test_history_webhook.py) | — | AC-1/2/3/4、E1/E7/E9 |

測試禁令:mock `httpx.post` 不發真實請求;chart 測試無 GUI(OO API 天然滿足);
不做像素比對。

## Out of Scope
- K 線圖(OHLC/candlestick)
- 技術指標疊圖(MA/RSI/BB 等)
- 查詢結果自動附圖(一律手動點按鈕)
- 中文圖表標籤與 Docker 字型安裝
- Dockerfile 任何修改
- webhook 路由 / grammar 既有 t/m/s/p step 行為變更
