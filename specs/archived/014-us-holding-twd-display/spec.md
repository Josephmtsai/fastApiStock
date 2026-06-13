# Spec — Feature 014: US Holding Display in TWD (H21)

## Overview

每日損益報告的「美股持倉」金額目前來自 yfinance 逐筆加總的 USD 值，改為直接讀取 Google Sheets **H21** 欄位（`portfolio_repo.fetch_pnl_us()`，已是 TWD），以 `NT$` 格式顯示。

---

## 現況 → 目標

| | 現況 | 目標 |
|---|---|---|
| 持倉資料來源 | `_calc_holding_pnl(us_held)` — yfinance unrealized_pnl 加總，USD | `portfolio_repo.fetch_pnl_us()` — Google Sheets H21，TWD |
| 持倉格式 | `持倉：+US$54,560.84` | `持倉：+NT$1,780,231` |
| 格式化函式 | `_fmt_us_amount()` | `_fmt_tw_amount()` |

## 報告格式對比

**現況**：
```
🇺🇸 美股今日：+US$1,257.93 (≈NT$40,883) ｜ 持倉：+US$54,560.84
```

**目標**：
```
🇺🇸 美股今日：+US$1,257.93 (≈NT$40,883) ｜ 持倉：+NT$1,780,231
```

---

## 資料流

```
Google Sheets H21 (TWD)
  → portfolio_repo.fetch_pnl_us() -> float | None
  → pnl_service.build_pnl_report() → us_holding_part
  → _fmt_tw_amount(pnl_us_twd) → "+NT$x,xxx,xxx"
  → _esc() → MarkdownV2 safe string
```

`portfolio_repo` 已被 `pnl_service.py` import，`fetch_pnl_us()` 已有 Redis cache + Google Sheets fallback。

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| H21 回傳 `None`（網路錯誤 / 試算表暫不可用） | `us_holding_part = ''`（不顯示持倉段），報告不中斷 |
| H21 值為負數 | `_fmt_tw_amount()` 正確輸出 `-NT$xxx`（符號已在 helper 處理） |
| H21 值為零 | 輸出 `+NT$0` |
| `us_today is None`（美股整體失敗） | 原有 `🇺🇸 美股：資料讀取失敗` 路徑不受影響 |
| 013 的 `(≈NT$...)` 今日換算 | 與 `us_holding_part` 獨立，不受影響 |

---

## Impact Analysis

| 元件 | 影響 |
|------|------|
| `pnl_service.build_pnl_report()` | 修改 `us_holding_part` 邏輯（~5 行） |
| `tests/test_pnl_service.py` | 更新 `test_build_pnl_report_holding_part_remains_usd_only`（改斷言 NT$）；新增 H21 None fallback 測試 |
| `portfolio_repo` | 無修改（`fetch_pnl_us()` 已存在） |
| `PortfolioEntry` dataclass | 無修改 |
| feature 013 邏輯 | 無影響 |

---

## Out of Scope

- 台股持倉顯示格式（不變）
- 今日損益的 USD→TWD 換算（013 功能，不變）
- `/pnl` Telegram 指令（使用不同 service path，不變）
