# Contract：Telegram 訊息格式規範

## 基本設定

| 項目 | 值 |
|------|-----|
| parse_mode | `MarkdownV2` |
| timeout | 10 秒 |
| API endpoint | `POST https://api.telegram.org/bot{TOKEN}/sendMessage` |

## MarkdownV2 Escape 規則

以下字元在 MarkdownV2 中必須加反斜線 escape：
`_ * [ ] ( ) ~ > # + - = | { } . !`

動態數值（股價、漲跌幅）必須透過 `_escape_md()` helper 處理，
絕對不在 f-string 中手動 escape。

## 台股訊息結構

```
📈 *台股定時推播*
🕐 {YYYY\-MM\-DD HH:MM} \| Asia/Taipei
\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-

{ARROW} *{SYMBOL}* {DISPLAY\_NAME}
   現價: `{PRICE} TWD`   昨收: `{PREV_CLOSE}`
   漲跌: `{SIGN}{CHANGE}` \({SIGN}{PCT}%\)
   RSI\(14\): `{RSI}` {RSI_TAG}
   均線: `MA20:{MA20}{DIR}  MA50:{MA50}{DIR}`
   近期區間: `{W52L} ─── {PRICE} ─── {W52H}` \({POS}%位置\)
   ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
   {VERDICT_EMOJI} *{VERDICT}* \(評分 {SCORE}/8\)
   {BULL\_REASONS}   ✅ {reason}
   {BEAR\_REASONS}   ❌ {reason}

\[以上重複每支股票\]

\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-
_由 FastAPI Stock Bot 自動產生_
```

## 美股訊息結構

與台股相同，以下差異：

- Header 改為：`📊 *美股定時推播*`
- 幣別標示改為：`{PRICE} USD`
- 昨收標示改為：`前收: \`{PREV_CLOSE}\``（美股用語）
- 盤前行（僅盤前時段有資料時顯示，台股不顯示）：
  `盤前: \`{PREMARKET_PRICE} USD\`  \({SIGN}{PCT}%\)`
  置於漲跌行之後、RSI 行之前

## 欄位替換說明

| 佔位符 | 說明 | 範例 |
|--------|------|------|
| `{ARROW}` | 漲跌箭頭 emoji | `🔺` / `🔻` |
| `{SYMBOL}` | 股票代碼 | `0050` / `AAPL` |
| `{DISPLAY_NAME}` | 公司名稱 | `元大台灣50` / `Apple Inc.` |
| `{PRICE}` | 現價，保留 2 位小數 | `195.50` |
| `{PREV_CLOSE}` | 前收，保留 2 位小數 | `193.20` |
| `{SIGN}` | 正負號 | `+` / (無) |
| `{CHANGE}` | 漲跌金額 | `2.30` |
| `{PCT}` | 漲跌幅，保留 2 位小數 | `1.19` |
| `{RSI}` | RSI 值，保留 1 位小數 | `58.3` |
| `{RSI_TAG}` | RSI 警示標注 | `⚠️超買` / `⚠️超賣` / 空 |
| `{DIR}` | 現價相對均線方向 | `↑` / `↓` |
| `{PREMARKET_PRICE}` | 美股盤前價（僅 US，盤前時段） | `196.00` |
| `{VERDICT_EMOJI}` | 判斷 emoji | `📈` / `📉` / `⚖️` |
| `{VERDICT}` | 判斷文字 | `看漲` / `看跌` / `中性觀望` |

## 缺值處理

當技術指標因歷史資料不足而為 `None` 時，對應行省略不顯示。
例如 RSI 行、MACD 行、布林行可能不出現在訊息中。

## 最大訊息長度

Telegram 單則訊息上限 4096 字元。若多支股票合計超過上限，
應分拆為多則訊息發送（每則最多 3 支股票）。

> Phase 1 暫不實作分拆邏輯，預期 3–5 支股票不會超過上限。
