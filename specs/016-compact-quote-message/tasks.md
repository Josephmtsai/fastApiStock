# Tasks 016 — compact-quote-message

> Branch: `feature/016-compact-quote-message`(自 main 建立,T0 先做)
> 完成定義(DoD,每個 task 通用):
> `uv run ruff check . --fix && uv run ruff format .`、
> `uv run mypy src/`、`uv run pytest` 全綠,覆蓋率 80%+。

## T0 — 建立 feature branch
- **目標**:自 `main` 建立 `feature/016-compact-quote-message`。
- **涉及檔案**:無。
- **驗收**:`git branch --show-current` 為 feature branch;禁止直接改 main。

## T1 — 新增 `_build_indicator_summary` helper
- **目標**:在 `src/fastapistock/services/telegram_service.py` 新增
  `_build_indicator_summary(stock: RichStockData) -> str | None`,
  依 spec Data Contracts 組裝 RSI / MACD / MA / BB / 量能五段落,
  以 ` │ `(U+2502)串接,全空回傳 None。
- **涉及檔案**:`src/fastapistock/services/telegram_service.py`
- **驗收標準**(對應 AC-1.1~1.7、E1~E6、E8、E9):
  - 五段落齊全時輸出順序與格式正確
  - 任一輸入 None / 0 時該段省略,無孤立分隔符
  - macd_hist == 0、bb range == 0、volume_avg20 == 0 不拋例外
  - 完整 type hints、Google Style docstring、無 `Any`、無 `print()`
  - 函式不超過 50 行

## T2 — 改造 `_format_rich_block` 與頁尾圖例
- **目標**:
  1. 移除獨立 RSI 行(原 line 337-341)
  2. 移除均線行(原 line 343-351)
  3. 移除 bull/bear reasons 輸出迴圈(原 line 388-391)
  4. 於持倉區塊之後、近期區間行之前插入
     `f'   {_escape_md(summary)}'`(summary 為 None 時不插入)
  5. `format_rich_stock_message` 頁尾,在 `_由 FastAPI Stock Bot 自動產生_`
     之前加入圖例行:`_✚金叉 ─死叉 ↑站上均線 ↓跌破均線 ⚠️超買/超賣_`
     (AC-5.1/5.2,每則訊息一行)
- **涉及檔案**:`src/fastapistock/services/telegram_service.py`
- **驗收標準**(對應 AC-2.1~2.4、AC-3.1~3.4、AC-4.1~4.2、AC-5.1~5.2、E7、E10):
  - 標題/價格/持倉/近期區間/評分結論/成本訊號行為與改動前逐字元一致
  - `format_rich_stock_message` 簽章不變;`webhook.py`、
    `_format_stock_message`、`indicators.py`、schema 零修改
  - 訊息無 `✅`/`❌`/`RSI\(14\)`/`均線:` 字樣
  - escape 後摘要行僅 `.` 被加上反斜線
  - 頁尾圖例行存在且僅一行

## T3 — 改寫必壞測試
- **目標**:更新 `tests/test_telegram_send_rich.py`:
  - `test_format_rich_block_rsi_overbought`(line 124):
    `assert '超買' in msg` → `assert 'RSI 75' in msg and '⚠️' in msg`
  - `test_format_rich_block_rsi_oversold`(line 142):
    `assert '超賣' in msg` → `assert 'RSI 25' in msg and '⚠️' in msg`
- **涉及檔案**:`tests/test_telegram_send_rich.py`
- **驗收標準**:兩測試綠燈;檔內其餘測試(send 錯誤路徑、BB tag)不動且綠燈。

## T4 — 新增摘要行測試
- **目標**:於 `tests/test_telegram_formatter.py` 新增
  `TestIndicatorSummaryLine` 測試類,涵蓋:
  1. 全指標齊全 → 摘要行含 `RSI`、`✚`、`MA20↑`、`MA50↑`、`量`(AC-1.1)
  2. rsi=55 → 無 ⚠️;rsi=70.0 / 30.0 → 有 ⚠️(AC-1.2/1.3、E9)
  3. macd_hist<0 → `─`(U+2500);macd_hist=0 → 無 `MACD`(AC-1.4、E3)
  4. bb 高檔/低檔/中間 → `BB 高檔`/`BB 低檔`/無 BB 段(AC-1.6、E5)
  5. bb_upper==bb_lower → 無 BB 段且不拋錯(E4)
  6. volume_avg20=0 → 無量能段(E6)
  7. 全指標 None + volume_avg20=0 → 訊息無 `│` 字元(E1)
  8. 部分指標 → 分隔符數 = 段落數 - 1,無頭尾 `│`(E2)
  9. `量 1\.8x` 的 `.` 已 escape;摘要行無未 escape 的 `-`/`+`/`|`(AC-4.1/4.2、E8)
  10. 無 `✅`/`❌`/`RSI\(14\)`/`均線:`(AC-2.1~2.3)
  11. 持倉區塊/近期區間/評分結論/盤前顯示照舊(AC-3.1、E7、E10)
  12. 頁尾圖例行存在且整則訊息僅出現一次(AC-5.1)
- **涉及檔案**:`tests/test_telegram_formatter.py`
- **驗收標準**:新測試全綠;既有測試零修改仍全綠
  (`test_rsi_line_*`、`TestPreMarketDisplay`、`TestCalcCostSignal`)。

## T5 — 全量驗證與提交
- **目標**:
  1. `uv run ruff check . --fix && uv run ruff format .`
  2. `uv run mypy src/`
  3. `uv run pytest`(覆蓋率 80%+)
  4. `uv run pre-commit run --all-files`
  5. Conventional Commit:`feat: compact rich quote message with symbol summary line`
  6. 產出 `specs/016-compact-quote-message/handoff-dev.json`
     並通知 orchestrator spawn **codex-reviewer**(非直接 QA)
- **涉及檔案**:全部異動檔案。
- **驗收標準**:所有 hook 通過;不 merge、不 deploy。

## AC 對照表

| Task | 對應 AC |
|------|---------|
| T1 | AC-1.1~1.7, E1~E6, E8, E9 |
| T2 | AC-2.1~2.4, AC-3.1~3.4, AC-4.1~4.2, AC-5.1~5.2, E7, E10 |
| T3 | 既有測試相容性 |
| T4 | 全部 AC 的測試覆蓋 |
| T5 | CLAUDE.md 品質門檻 |
