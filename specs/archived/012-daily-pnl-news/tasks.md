# Tasks — Spec 012 Daily P&L + News Sentiment

## Task Checklist

### T1 — news_repo.py
- [ ] Create `src/fastapistock/repositories/news_repo.py`
- [ ] Create `tests/test_news_repo.py`
- [ ] AC: fetch_news returns list[NewsItem]; Redis cache hit skips yfinance call
- [ ] AC: Redis miss triggers random sleep + yfinance call + cache write
- [ ] AC: yfinance failure returns empty list (no raise)

### T2 — news_service.py
- [ ] Create `src/fastapistock/services/news_service.py`
- [ ] Create `tests/test_news_service.py`
- [ ] AC: classify_sentiment returns 正面/中性/負面 by keyword
- [ ] AC: get_sentiment_news returns max_items items
- [ ] AC: empty news list → empty result

### T3 — pnl_service.py (core logic)
- [ ] Create `src/fastapistock/services/pnl_service.py`
- [ ] Create `tests/test_pnl_service.py`
- [ ] AC: today's TW total = sum(stock.change * stock.shares) for held stocks
- [ ] AC: today's US total = sum(stock.change * stock.shares) for held stocks
- [ ] AC: stocks with None shares excluded from totals
- [ ] AC: one market exception → that market shows error, other renders normally

### T4 — pnl_service.py (message formatting)
- [ ] Modify `src/fastapistock/services/pnl_service.py`
- [ ] Modify `tests/test_pnl_service.py`
- [ ] AC: message contains header, TW section, US section
- [ ] AC: each stock row has 現價, 今日, 持倉損益 lines
- [ ] AC: news lines show 📰 title [sentiment]
- [ ] AC: message > 4096 chars splits into multiple segments
- [ ] AC: all dynamic text MarkdownV2-escaped

### T5 — webhook.py update
- [ ] Modify `src/fastapistock/routers/webhook.py`
- [ ] Modify `tests/test_webhook.py`
- [ ] AC: /pnl dispatches to pnl_service.build_pnl_report()
- [ ] AC: each segment sent with parse_mode='MarkdownV2'

### T6 — scheduler.py new jobs
- [ ] Modify `src/fastapistock/scheduler.py`
- [ ] Modify `tests/test_scheduler.py`
- [ ] AC: TW job fires at 14:35 Taipei on weekdays
- [ ] AC: US job fires at 04:05 Taipei Tue–Sat
- [ ] AC: both jobs call pnl_service.build_pnl_report() and send each segment
