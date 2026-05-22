# Spec 012 — 每日 P&L + 新聞情緒

**Date**: 2026-05-22
**Role**: fastapistock-sa
**Status**: Ready for implementation

---

## Overview

強化現有 `/pnl` 指令，並新增收盤定時推播。v1 `/pnl` 只顯示帳戶總覽未實現損益；
本 spec 加入三個層次：

1. **帳戶總覽** — 台股今日漲跌損益合計 + 美股今日漲跌損益合計
2. **個股明細** — 每支持倉的今日漲跌（change × shares）與持倉未實現損益
3. **新聞情緒** — 每支持倉最多 2 則近期新聞標題 + keyword-based 情緒標籤

收盤後自動推播（台股 14:35、美股 04:05 Taipei），格式相同。

---

## User Stories

### US1 — 手動查詢當日損益
作為長期投資者，我輸入 `/pnl` 看到帳戶總覽與每支持倉的今日損益及新聞情緒。

### US2 — 收盤後自動推播
作為長期投資者，台股 / 美股收盤後自動收到完整損益報告。

### US3 — 新聞情緒快速掃描
作為長期投資者，每支持倉顯示近期新聞標題與情緒分類，快速判斷是否需要深入研究。

---

## Acceptance Criteria

| AC | Description |
|----|-------------|
| AC1 | `/pnl` 回覆包含帳戶總覽（台股今日損益合計 + 美股今日損益合計） |
| AC2 | 每支 TW 持倉顯示：現價、今日漲跌點數與%、持倉未實現損益 |
| AC3 | 每支 US 持倉顯示：現價、今日漲跌點數與%、持倉未實現損益 |
| AC4 | 每支持倉最多 2 則新聞標題 + [正面]/[中性]/[負面] 情緒標籤 |
| AC5 | 台股週一–五 14:35 Taipei 自動推播，美股週二–六 04:05 Taipei 自動推播 |
| AC6 | 非交易日 scheduler 不推播 |
| AC7 | 訊息超過 4096 字元時自動分段連續發送 |
| AC8 | 任一市場 / 個股 / 新聞抓取失敗時顯示對應提示，不影響其餘部分 |

---

## Message Format

```
📊 每日損益報告 2026-05-22

💰 帳戶總覽
🇹🇼 台股今日：+NT$12,450
🇺🇸 美股今日：-US$320

──────────────
🇹🇼 台股明細

2330 台積電
現價 920 | 今日 +15 (+1.66%)
持倉損益 +NT$45,000
📰 AI晶片需求強勁 [正面]
📰 外資連續買超3日 [正面]

──────────────
🇺🇸 美股明細

AAPL
現價 $190.20 | 今日 -3.20 (-1.65%)
持倉損益 -US$800
📰 iPhone 16備貨訊號強 [正面]
```

---

## Modules

### New

| File | Responsibility |
|------|---------------|
| `src/fastapistock/repositories/news_repo.py` | yfinance news fetch + Redis cache (TTL 4h) + random sleep |
| `src/fastapistock/services/news_service.py` | keyword-based sentiment classification → `SentimentNews` |
| `src/fastapistock/services/pnl_service.py` | orchestrate P&L + news → MarkdownV2 segments |

### Modified

| File | Change |
|------|--------|
| `src/fastapistock/routers/webhook.py` | `/pnl` dispatch → `pnl_service.build_pnl_report()` with MarkdownV2 + multi-segment |
| `src/fastapistock/scheduler.py` | Add TW 14:35 + US 04:05 cron jobs calling `pnl_service` |

---

## Key Data Flow

```
/pnl command
  → pnl_service.build_pnl_report(now)
      → portfolio_repo.fetch_portfolio()           # TW symbols
      → portfolio_repo.fetch_portfolio_us()        # US symbols
      → stock_service.get_rich_tw_stocks(symbols)  # RichStockData with avg_cost/shares/change
      → us_stock_service.get_us_stocks(symbols)    # same for US
      → news_service.get_sentiment_news(symbol, market)
            → news_repo.fetch_news(symbol, market) # Redis cache → yfinance
  → reply_to_chat (MarkdownV2, multi-segment)
```

---

## Key Types

```python
# news_repo.py
@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str

# news_service.py
@dataclass(frozen=True)
class SentimentNews:
    title: str
    sentiment: Literal['正面', '中性', '負面']
```

---

## Edge Cases

| Case | Behavior |
|------|----------|
| No TW holdings | Show `🇹🇼 台股：目前無持股` |
| No US holdings | Show `🇺🇸 美股：目前無持股` |
| One market fails | Show `資料讀取失敗`，other market normal |
| Stock missing change/shares | Skip today P&L line |
| News API fails / no news | Show `暫無新聞` |
| Redis unavailable | Skip cache, fetch directly with random sleep |
| Message > 4096 chars | Split into multiple segments |

---

## Out of Scope

- AI/LLM sentiment analysis
- News full text or summary
- Historical P&L comparison beyond today
- Portfolio performance charts
- `/news [symbol]` per-stock deep dive
- Buy/sell recommendations
