# Spec 016 — Telegram Rich 推播訊息符號化精簡 (compact-quote-message)

## Overview

將 `_format_rich_block()` 中的獨立 RSI 行、均線行與所有 bull/bear 理由行(最多 10 行)
合併為單一符號摘要行,使每檔股票的推播區塊由最多 14 行縮減至最多 10 行
(無持倉時 6 行),且不改變任何對外介面與評分邏輯。

## Branch

- Feature branch: `feature/016-compact-quote-message`(自 `main` 建立)
- 禁止直接 commit 到 `main`

## User Stories

### US-1 符號摘要行

As a 投資人, I want 推播訊息以單行符號摘要呈現技術指標,
so that 我在手機上能一眼掃完多檔股票而不需捲動長篇理由文字。

- **AC-1.1** Given 一檔股票所有指標齊全(rsi=72, macd_hist>0, price>ma20,
  price>ma50, bb_pos>0.85, volume/volume_avg20=1.8),
  When 呼叫 `format_rich_stock_message`,
  Then 訊息包含一行(escape 後)形如:
  `RSI 72⚠️ │ MACD ✚ │ MA20↑ MA50↑ │ BB 高檔 │ 量 1\.8x`
- **AC-1.2** Given rsi=55(介於 30–70),
  When 產生摘要行, Then RSI 段為 `RSI 55`(無 ⚠️)。
- **AC-1.3** Given rsi>=70 或 rsi<=30,
  When 產生摘要行, Then RSI 段附加 ⚠️(沿用現有顯示閾值)。
- **AC-1.4** Given macd_hist > 0 → `MACD ✚`;macd_hist < 0 → `MACD ─`
  (U+2500,非 ASCII 減號)。
- **AC-1.5** Given price > ma20 → `MA20↑`,price <= ma20 → `MA20↓`;
  MA50 同理;兩者同屬一個段落,以單一空格分隔。
- **AC-1.6** Given bb_pos = (price - bb_lower) / (bb_upper - bb_lower),
  When bb_pos > 0.85 → `BB 高檔`;bb_pos < 0.15 → `BB 低檔`;
  其餘(含 0.15–0.85)→ BB 段整段不顯示(沿用 `score_stock` 閾值)。
- **AC-1.7** Given volume > 0 且 volume_avg20 > 0,
  When 產生摘要行, Then 量能段為 `量 {ratio:.1f}x`(ratio = volume / volume_avg20)。

### US-2 移除膨脹區塊

As a 投資人, I want 移除逐條理由與重複的指標行,
so that 訊息不再因 8 行理由而過長。

- **AC-2.1** 訊息中不得出現 `RSI(14):` 舊格式行(escape 前字面 `RSI\(14\):`)。
- **AC-2.2** 訊息中不得出現 `均線:` 行。
- **AC-2.3** 訊息中不得出現任何 `✅` 或 `❌` 開頭的理由行。
- **AC-2.4** `score_stock()` 的 `ScoreResult` 介面(score/verdict/
  bull_reasons/bear_reasons)不得變更;`indicators.py` 不修改。
  (developer 可選擇不迭代 reasons,但不得改動 ScoreResult 欄位。)

### US-3 保留既有區塊與介面

As a 系統維運者, I want 其餘功能完全不受影響,
so that webhook 指令與排程推播行為一致。

- **AC-3.1** 下列區塊保留且格式不變:標題行(arrow+symbol+名稱)、
  價格/漲跌行(`_build_price_change_lines`,含盤前邏輯)、持倉區塊
  (持股/成本/損益)、近期區間行(52 週位置)、`┄` 分隔線、
  評分結論行(`📈 *偏看漲* \(評分 x/8\)`)、成本訊號行(`_calc_cost_signal`)。
- **AC-3.2** `format_rich_stock_message(stocks, market, now)` 函式簽章不變;
  `src/fastapistock/routers/webhook.py`(line 194、224)與
  `send_rich_stock_message` 呼叫端不修改。
- **AC-3.3** `_format_stock_message`(StockData 6 行台股簡訊版)不修改。
- **AC-3.4** `RichStockData` schema 不修改。

### US-4 MarkdownV2 正確性

As a 系統維運者, I want 新符號行通過 Telegram MarkdownV2 解析,
so that 推播不會因 400 Bad Request 而失敗。

- **AC-4.1** 摘要行中的 `.`(如 `1.8x`)必須 escape 為 `1\.8x`
  (整行內容經 `_escape_md` 處理;`│`/`─`/`⚠️`/`✚`/`↑↓` 非保留字元,
  escape 後不變)。
- **AC-4.2** 摘要行不得使用 ASCII `-`、`+`、`|` 未 escape 字元
  (MACD 負值用 `─` U+2500、分隔用 `│` U+2502、正值用 `✚`)。

### US-5 頁尾符號圖例(orchestrator 依使用者討論補充)

As a 投資人, I want 訊息頁尾有一行符號圖例,
so that 第一次看新格式也能理解符號意義。

- **AC-5.1** `format_rich_stock_message` 頁尾,在 `_由 FastAPI Stock Bot 自動產生_`
  之前加入一行斜體圖例(escape 後):
  `_✚金叉 ─死叉 ↑站上均線 ↓跌破均線 ⚠️超買/超賣_`。
  每則訊息僅一行,不隨股票數量增加。
- **AC-5.2** 圖例行通過 MarkdownV2 解析(斜體 `_..._`,內文經 `_escape_md`;
  `/` 非保留字元)。

## Modules

| Module | 職責 | 涉及檔案 | 動作 |
|--------|------|---------|------|
| indicator_summary | 新增 `_build_indicator_summary(stock) -> str \| None`:組裝符號摘要行,全段落缺失時回傳 None | `src/fastapistock/services/telegram_service.py` | 新增 private helper |
| rich_block | `_format_rich_block()`:移除 RSI 行(line 337-341)、均線行(line 343-351)、reasons 迴圈(line 388-391),於持倉區塊之後、近期區間行之前插入摘要行 | `src/fastapistock/services/telegram_service.py` | 修改 |
| footer_legend | `format_rich_stock_message()`:頁尾加入符號圖例行 | `src/fastapistock/services/telegram_service.py` | 修改 |
| tests_formatter | 更新/新增格式測試 | `tests/test_telegram_formatter.py` | 修改 + 新增 |
| tests_send_rich | 改寫 2 個必壞測試 | `tests/test_telegram_send_rich.py` | 修改 |

## Data Contracts

輸入沿用既有 `RichStockData`(不變)。新 helper 契約:

```python
def _build_indicator_summary(stock: RichStockData) -> str | None:
    """Build the one-line symbol summary, e.g. 'RSI 72⚠️ │ MACD ✚ │ ...'.

    Segments (in order): RSI, MACD, MA20/MA50, BB, Volume.
    - RSI: f'RSI {rsi:.0f}' + ('⚠️' if rsi >= 70 or rsi <= 30 else '');
      omitted when stock.rsi is None.
    - MACD: 'MACD ✚' when macd_hist > 0; 'MACD ─' when macd_hist < 0;
      omitted when macd_hist is None or == 0.
    - MA: f'MA20{arrow}' (+ ' ' + f'MA50{arrow}' when ma50 present);
      arrow = '↑' if price > ma else '↓'; segment omitted when both None.
    - BB: 'BB 高檔' when bb_pos > 0.85; 'BB 低檔' when bb_pos < 0.15;
      omitted otherwise, or when bb_upper/bb_lower is None or range <= 0.
    - Volume: f'量 {volume / volume_avg20:.1f}x';
      omitted when volume <= 0 or volume_avg20 <= 0.

    Segments joined with ' │ ' (U+2502). Returns None when no segment exists.
    Caller escapes via _escape_md and prefixes '   ' indentation.
    """
```

輸出訊息(escape 後,含持倉範例):

```
🔺 *2330* 台積電
   最後成交: `1050.00 TWD`   昨收: `1020.00`   漲跌: `+30.00` \(\+2\.94%\)
   ─── 持倉 ───
   持股: `1,000`   成本: `900.00` \(\+16\.67%\)
   損益: `+150,000 TWD`
   RSI 72⚠️ │ MACD ✚ │ MA20↑ MA50↑ │ BB 高檔 │ 量 1\.8x
   近期區間: `800.00 ─── 1050.00 ─── 1100.00` \(83%位置\)
   ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
   📈 *偏看漲* \(評分 4/8\)
```

## API Design

無新增 API 路由。純訊息格式變更,webhook `/tw`、`/us` 指令與 scheduler
推播自動套用新格式。

## Edge Cases

| # | 情境 | 預期行為 |
|---|------|---------|
| E1 | 所有指標 None 且 volume_avg20=0 | 摘要行整行不輸出(不留空行、不留孤立 `│`) |
| E2 | 只有部分指標(如僅 rsi + ma20) | 只輸出存在段落:`RSI 55 │ MA20↑`,分隔符數量 = 段落數 - 1,無頭尾 `│` |
| E3 | macd_hist == 0 | MACD 段省略(非 ✚ 非 ─) |
| E4 | bb_upper == bb_lower(range 為 0) | BB 段省略,不得除以零 |
| E5 | bb_pos 介於 0.15–0.85 | BB 段省略 |
| E6 | volume_avg20 == 0 或 volume == 0 | 量能段省略,不得除以零 |
| E7 | 無持倉(avg_cost/shares None) | 持倉區塊照舊省略,摘要行緊接價格行之後 |
| E8 | ratio 帶小數(1.8) | 輸出 `量 1\.8x`(`.` 已 escape),Telegram 可解析 |
| E9 | rsi 剛好 70.0 / 30.0 | 附 ⚠️(>= / <= 閾值,與現有 RSI 行一致) |
| E10 | US 盤前狀態(premarket_price 有值) | 價格行維持盤前邏輯,摘要行照常輸出,互不影響 |

## Affected Tests(既有測試盤點)

**必壞、需改寫:**
- `tests/test_telegram_send_rich.py::test_format_rich_block_rsi_overbought`
  (line 124-139,斷言 `'超買' in msg`;該文字僅存在於被移除的 RSI 行
  與 bear reason)→ 改斷言 `'RSI 75' in msg` 且 `'⚠️' in msg`
- `tests/test_telegram_send_rich.py::test_format_rich_block_rsi_oversold`
  (line 142-157,斷言 `'超賣' in msg`)→ 改斷言 `'RSI 25' in msg` 且 `'⚠️' in msg`

**仍通過、建議強化:**
- `tests/test_telegram_formatter.py::test_rsi_line_present_when_not_none`
  (line 87)、`test_rsi_line_absent_when_none`(line 93)→ 保留並補斷言
  舊格式 `RSI\(14\)` 不存在
- `test_macd_indicator_line_not_in_message`(line 115,斷言 `'MACD:' not in msg`,
  新格式無冒號)→ 保留
- `test_bollinger_not_in_message`(line 122,斷言 `'布林' not in msg`,
  reasons 移除後恆真)→ 保留
- `test_negative_score_dash_escaped`(line 149)、`TestPreMarketDisplay` 全部、
  `TestCalcCostSignal` 全部 → 不受影響

## Out of Scope

- `_format_stock_message`(台股簡訊 6 行版)任何變更
- `score_stock()` 評分邏輯、閾值、reasons 文字調整
- `RichStockData` / `ScoreResult` schema 變更
- 訊息長度上限(4096 字元)分頁機制
- 使用者自訂顯示格式偏好
