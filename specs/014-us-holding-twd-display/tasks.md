# Tasks — Feature 014: US Holding Display in TWD (H21)

---

## Task 014-1: 修改 `build_pnl_report()` 的持倉顯示

**目標**: 將 `us_holding_part` 從 yfinance USD 加總改為 `fetch_pnl_us()` H21 TWD 值。

**涉及檔案**:
- `src/fastapistock/services/pnl_service.py`
- `tests/test_pnl_service.py`

**變更內容**:

1. `build_pnl_report()` 中，在 `us_holding_part` 組裝前加入：
   ```python
   pnl_us_twd: float | None = None
   try:
       pnl_us_twd = portfolio_repo.fetch_pnl_us()
   except Exception:
       logger.warning('fetch_pnl_us raised unexpectedly; holding part hidden')
   ```

2. 將 `us_holding_part` 替換為：
   ```python
   us_holding_part = (
       f' ｜ 持倉：{_esc(_fmt_tw_amount(pnl_us_twd))}'
       if pnl_us_twd is not None
       else ''
   )
   ```
   （移除舊的 `_calc_holding_pnl(us_held)` 路徑）

3. `tests/test_pnl_service.py`：
   - 將 `test_build_pnl_report_holding_part_remains_usd_only` 改為 `test_build_pnl_report_holding_part_displays_twd`，patch `portfolio_repo.fetch_pnl_us` 回傳 `1_780_231.0`，斷言輸出含 `NT$1,780,231`
   - 新增 `test_build_pnl_report_holding_hidden_when_pnl_us_none`：patch `fetch_pnl_us` 回傳 `None`，斷言 `us_holding_part` 段（`持倉：`）不出現在輸出中

**Acceptance Criteria**:

- AC-1: `fetch_pnl_us()` 回傳 `1_780_231.0` 時，報告含 `持倉：\+NT\$1,780,231`（MarkdownV2 escaped）
- AC-2: `fetch_pnl_us()` 回傳 `None` 時，報告不含 `持倉：` 段，且報告正常送出（不 raise）
- AC-3: `fetch_pnl_us()` 拋出 Exception 時，`us_holding_part = ''`，報告不中斷
- AC-4: 今日損益 `(≈NT$...)` 換算段格式不受影響（013 功能無迴歸）
- AC-5: 台股持倉格式 `持倉：+NT$xx,xxx,xxx` 不受影響
- AC-6: `us_today is None` 路徑輸出 `🇺🇸 美股：資料讀取失敗`（既有行為不變）
- AC-7: `uv run pytest tests/test_pnl_service.py` passes（新舊測試全過）
- AC-8: `uv run mypy src/` passes
- AC-9: `uv run ruff check . --fix && uv run ruff format .` passes

---

## 測試覆蓋

| 測試案例 | 方式 |
|---------|------|
| H21 有值 → `NT$` 顯示 | mock `portfolio_repo.fetch_pnl_us` = `1780231.0` |
| H21 None → 持倉段隱藏 | mock `portfolio_repo.fetch_pnl_us` = `None` |
| H21 Exception → 報告不中斷 | mock `portfolio_repo.fetch_pnl_us` raises `Exception` |
| 013 今日換算無迴歸 | 既有測試覆蓋 |
