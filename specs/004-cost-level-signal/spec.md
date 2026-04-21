# Spec 004 — 持倉成本位階訊號 (Cost Level Signal)

**狀態**: 需求確認完畢，可開發
**日期**: 2026-04-21
**討論狀態**: SA 需求討論已完成，可直接交開發者實作

---

## 背景與目標

使用者為長期投資者（5~10 年持有期），採定期定額 + 手動加碼策略，每月固定投入台股 10 萬。
目前系統每次推播只顯示股價與未實現損益，缺乏「是否適合加碼」的參考訊號。

本功能在現有盤中推播訊息的個股區塊中，新增一行「成本位階訊號」，讓使用者一眼判斷目前是否進入加碼區間。

---

## 使用者投資策略

- 持股性質：長期存股，預期 10 年持有
- 加碼策略：下跌一定幅度後分批加碼
- 訊號需求：距離均攤成本跌幅 + MA50 跌破，兩者同時成立才觸發
- 無須冷卻期（每次推播都重新計算顯示）

---

## 功能規格

### 觸發條件（兩者同時成立）

| 市場 | 條件 1 | 條件 2 |
|------|--------|--------|
| 台股 | 現價距均攤成本跌幅 ≥ -15% | 現價 < MA50 |
| 美股 | 現價距均攤成本跌幅 ≥ -20% | 現價 < MA50 |

### 訊號等級

跌幅公式：`pnl_pct = (現價 - 均攤成本) / 均攤成本 × 100`

**台股**

| 等級 | 跌幅區間 | 顯示 |
|------|---------|------|
| ⭐ | -15% ~ -20% | 🟠 ⭐ |
| ⭐⭐ | -20% ~ -25% | 🔴 ⭐⭐ |
| ⭐⭐⭐ | ≤ -25% | 🔴 ⭐⭐⭐ |

**美股**

| 等級 | 跌幅區間 | 顯示 |
|------|---------|------|
| ⭐ | -20% ~ -25% | 🟠 ⭐ |
| ⭐⭐ | -25% ~ -30% | 🔴 ⭐⭐ |
| ⭐⭐⭐ | ≤ -30% | 🔴 ⭐⭐⭐ |

### 呈現方式

- **位置**：嵌入現有個股區塊底部（`_format_rich_block()` 最後一行）
- **沒有訊號時**：整行不顯示，不影響原本版面
- **有訊號時**，格式如下：

```
   💰 加碼訊號 🔴 ⭐⭐  距成本 -22.3%  |  MA50 已跌破
```

---

## 邊界條件

| 情境 | 處理方式 |
|------|---------|
| `avg_cost` 為 `None` 或 `0` | 整行略過，不顯示訊號 |
| 純追蹤股票（無持倉成本） | 整行略過 |
| MA50 資料不存在 | 條件 2 視為未成立，不觸發 |
| `pnl_pct` 計算結果為 NaN/Inf | 整行略過，記錄 warning log |

---

## 不在範圍（Out of Scope）

- 不新增任何 FastAPI 路由或 Telegram 指令
- 不修改 `RichStockData`、`PortfolioEntry` 資料結構
- 不提供加倉金額或停損建議
- 不改動技術指標評分（`score_stock`）邏輯
- 不支援使用者自訂門檻（固定寫死為 module-level constants）
- 不新增獨立警示通知（只嵌入現有推播）

---

## 資料欄位確認

| 欄位 | 來源 | 說明 |
|------|------|------|
| `avg_cost` | `RichStockData.avg_cost: float \| None` | 從 portfolio sheet 注入，台股來自 GID=1004709448（`GOOGLE_SHEETS_PORTFOLIO_GID_TW`） |
| `ma50` | `RichStockData.ma50: float \| None` | 已在 `_format_rich_block()` 可直接存取 |
| 美股 `avg_cost` | `RichStockData.avg_cost` | 來自 `GOOGLE_SHEETS_PORTFOLIO_GID_US`，同一套路 |

門檻常數寫在 `telegram_service.py` 頂部（module-level constants），不進 `.env`。

---

## 涉及檔案

### 主要實作

- `src/fastapistock/services/telegram_service.py`
  - 新增 module-level 門檻常數（`_TW_SIGNAL_THRESHOLDS`、`_US_SIGNAL_THRESHOLDS`）
  - 新增 `_calc_cost_signal()` 輔助函式
  - 修改 `_format_rich_block()` 插入訊號行

### 新增 env var（config 擴充）

- `src/fastapistock/config.py`
  - 新增 `GOOGLE_SHEETS_TW_TRANSACTIONS_GID`（交易紀錄 tab，GID=1491901018）
  - 目前 Cost Level Signal 不使用此值，但統一管理所有 GID

### 測試

- `tests/test_telegram_formatter.py`
  - 新增等級計算邏輯的單元測試（台股 / 美股各等級）
  - 新增邊界條件測試（None、0、MA50 缺失、NaN）

---

## 門檻常數（供開發者參考）

```python
# 台股
_TW_SIGNAL_THRESHOLDS = [
    (-25.0, '🔴', '⭐⭐⭐'),
    (-20.0, '🔴', '⭐⭐'),
    (-15.0, '🟠', '⭐'),
]

# 美股
_US_SIGNAL_THRESHOLDS = [
    (-30.0, '🔴', '⭐⭐⭐'),
    (-25.0, '🔴', '⭐⭐'),
    (-20.0, '🟠', '⭐'),
]
```
