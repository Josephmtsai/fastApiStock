# Spec 012 — 每日 P&L + 新聞情緒整合

**Date**: 2026-05-21
**Role**: fastapistock-sa
**Status**: Approved — ready for implementation planning
**Feature**: 012-daily-pnl-news

---

## Overview

新增 Telegram `/pnl` 指令與收盤後定時推播，提供：

1. **帳戶層級損益總覽** — 台股合計 + 美股合計當日損益與報酬率
2. **個股明細** — 每支持倉的今日損益（現價 vs 昨收）與持倉損益（現價 vs 均價）
3. **新聞情緒** — 每支持倉最多 2 則近期新聞標題 + 情緒標籤（正面 / 中性 / 負面）

成本均價已記錄於 Google Sheets 投資組合，直接讀取使用。

---

## User Stories

### US1 — 手動查詢當日損益

身為長期投資者，我想隨時輸入 `/pnl` 看到完整的帳戶與個股損益，
不需要切換到其他 App。

### US2 — 收盤後自動推播

身為長期投資者，我希望台股 / 美股收盤後自動收到損益報告，
不需要記得手動查詢。

### US3 — 新聞情緒快速掃描

身為長期投資者，我想在損益報告裡看到每支持倉的近期新聞標題與情緒分類，
讓我快速判斷是否需要深入研究。

---

## Acceptance Criteria

### AC1 — `/pnl` dispatch

Given 授權 Telegram 用戶發送 `/pnl`
When webhook 接收訊息
Then bot 回覆 MarkdownV2 格式的完整損益 + 新聞報告。

### AC2 — 帳戶總覽

Given TW 和 US 投資組合存在
When `/pnl` 執行
Then 回覆包含台股合計損益（NT$金額 + %）與美股合計損益（US$金額 + %）。

### AC3 — 個股明細

Given 持倉均價已記錄於 Google Sheets
When `/pnl` 計算
Then 每支股票顯示：現價、今日漲跌（點數 + %）、持倉損益（金額 + %）。

### AC4 — 新聞情緒

Given yfinance 新聞可取得
When `/pnl` 組合訊息
Then 每支股票最多顯示 2 則新聞標題，各附情緒標籤 [正面] / [中性] / [負面]。

### AC5 — 收盤定時推播

Given 台股週一–五 14:35 Taipei / 美股週二–六 04:05 Taipei
When scheduler 觸發
Then 發送與 `/pnl` 相同格式的完整報告給授權用戶。

### AC6 — 非交易日不推播

Given 週末或非 market window
When scheduler 觸發
Then 不發送任何訊息（沿用現有 market window 判斷邏輯）。

### AC7 — 訊息分段

Given Telegram 單訊息上限 4096 字元
When 報告超過上限
Then 自動切分為多段連續發送，不截斷。

### AC8 — 部分失敗容錯

Given 某市場 / 個股 / 新聞 API 失敗
When `/pnl` 組合訊息
Then 失敗的部分顯示對應提示，其餘正常呈現，不拋出 500。

---

## 訊息格式

```
📊 每日損益報告 2026-05-21

💰 帳戶總覽
🇹🇼 台股：+NT$12,450 (+2.3%)
🇺🇸 美股：-US$320 (-0.8%)

──────────────────
🇹🇼 台股明細

2330 台積電
現價 920 | 今日 +15 (+1.66%)
持倉損益 +NT$45,000 (+12.3%)
📰 AI晶片需求強勁，台積電Q2展望樂觀 [正面]
📰 外資連續買超3日 [正面]

0050 元大台灣50
現價 185 | 今日 -2 (-1.07%)
持倉損益 +NT$8,500 (+5.2%)
📰 ETF資金流入創月新高 [正面]

──────────────────
🇺🇸 美股明細

AAPL Apple Inc.
現價 $190.20 | 今日 -3.20 (-1.65%)
持倉損益 -US$800 (-4.1%)
📰 iPhone 16備貨訊號強 [正面]
📰 Apple Vision Pro銷量低於預期 [負面]
```

---

## 模組設計

### 新增模組

#### `src/fastapistock/repositories/news_repo.py`

職責：
- 呼叫 `yfinance ticker.news` 抓取新聞
- Redis cache，key: `news:{symbol}`，TTL: 4 小時
- 實作 random sleep（0.5–1.5s）與 timeout
- 回傳 `list[NewsItem]`（dataclass: `title: str`, `url: str`）

#### `src/fastapistock/services/news_service.py`

職責：
- 接收 `list[NewsItem]`，以 keyword 規則分類情緒
- 正面關鍵字：強勁、樂觀、買超、創高、成長、上漲、突破、beat、surge、rally
- 負面關鍵字：下滑、虧損、賣超、暴跌、警告、miss、drop、decline、downgrade
- 未匹配 → 中性
- 回傳 `list[SentimentNews]`（dataclass: `title: str`, `sentiment: Literal['正面','中性','負面']`）

#### `src/fastapistock/services/pnl_service.py`

職責：
- `build_pnl_report(now: datetime) -> str`：公開入口，供 webhook 與 scheduler 呼叫
- 讀取 TW + US 投資組合（均價 + 股數）
- 呼叫現有 `stock_service.get_rich_tw_stocks()` / `us_stock_service.get_us_stocks()` 取現價
- 計算今日損益（現價 - 昨收）× 股數
- 計算持倉損益（現價 - 均價）× 股數
- 呼叫 `news_service` 取情緒新聞
- 組合 MarkdownV2 字串，超過 4096 字元時切分為 `list[str]`

### 修改模組

#### `src/fastapistock/routers/webhook.py`

- `_HELP_TEXT` 加入 `/pnl` 說明
- `_dispatch_message()` 加入 `/pnl` 分支
- 呼叫 `pnl_service.build_pnl_report()`
- 使用 `parse_mode='MarkdownV2'`，支援多段發送

#### `src/fastapistock/scheduler.py`

- 新增台股收盤 job：`CronTrigger(hour=14, minute=35, timezone=_TZ)`，週一–五
- 新增美股收盤 job：`CronTrigger(hour=4, minute=5, timezone=_TZ)`，週二–六
- 兩個 job 均呼叫 `pnl_service.build_pnl_report()` 後以 `send_text_message` 推送

---

## 資料契約

### PortfolioEntry（現有，確認含均價欄位）

```python
@dataclass
class PortfolioEntry:
    symbol: str
    shares: float
    avg_cost: float  # 確認此欄位存在於 Google Sheets
```

### NewsItem

```python
@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
```

### SentimentNews

```python
@dataclass(frozen=True)
class SentimentNews:
    title: str
    sentiment: Literal['正面', '中性', '負面']
```

---

## 錯誤處理

| 情境 | 行為 |
|------|------|
| 台股 / 美股整體資料失敗 | 該市場顯示 `資料讀取失敗`，另一市場正常 |
| 某支個股現價缺失 | 顯示 `現價不可用`，損益欄位跳過 |
| Google Sheets 均價欄位空白 | 顯示 `成本未設定` |
| 新聞 API 失敗 / 無新聞 | 顯示 `暫無新聞`，P&L 正常顯示 |
| Redis 不可用 | 新聞 cache 跳過，直接抓取 |
| 訊息超過 4096 字元 | 自動分段連續發送 |
| 非交易日定時觸發 | 不推送（沿用 market window 判斷） |

---

## 安全 / 限流

- `/pnl` 走現有 webhook 路由，已有 Telegram secret 驗證與授權用戶 ID 檢查
- 使用現有 webhook rate limit bucket，不新增獨立限流設定
- `news_repo` 實作 random sleep 保護 Yahoo Finance upstream

---

## Out of Scope

- AI / LLM 情緒分析（v1 使用 keyword-based）
- 新聞全文或摘要
- 個股歷史 P&L（只顯示今日 + 持倉損益）
- 投資組合績效圖表
- `/news [symbol]` 單股新聞深挖指令
- 買賣建議或目標價
- 多用戶支援

---

## 模組依賴圖

```
webhook.py / scheduler.py
  └── pnl_service.py
        ├── portfolio_repo.py        (現有)
        ├── stock_service.py         (現有)
        ├── us_stock_service.py      (現有)
        └── news_service.py          (新增)
              └── news_repo.py       (新增)
                    └── Redis cache  (現有)
```
