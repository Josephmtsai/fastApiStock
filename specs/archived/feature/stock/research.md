# Phase 0 Research：定時股票推播排程

## 1. APScheduler 選版策略

**Decision**: 使用 APScheduler 3.x (`apscheduler>=3.10,<4`)

**Rationale**:
- APScheduler 4.x 為 asyncio-native 但 API 大幅改變，文件仍不成熟
- 3.x 的 `AsyncIOScheduler` 已與 FastAPI `lifespan` 整合良好，社群範例豐富
- 3.x 可直接在 FastAPI asyncio event loop 上運行，不需額外 thread

**Alternatives Considered**:
- Celery + Redis Beat：過重，Phase 1 單用戶不需要，且要跑額外 worker process
- 系統 cron：Railway 不支援，且需要額外 curl 打 API，不夠整合

**Integration Pattern**:
```python
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler(timezone='Asia/Taipei')
    scheduler.add_job(push_job, 'interval', minutes=30)
    scheduler.start()
    yield
    scheduler.shutdown()
```

---

## 2. US Stock 資料抓取

**Decision**: 沿用 yfinance（已在 dependencies），不引入新 HTTP 客戶端

**Rationale**:
- 專案已依賴 yfinance，新增 US stock repo 只需去掉 `.TW` suffix 即可
- Constitution IV 規定不得引入重複功能的新機制
- yfinance `ticker.history(period='6mo')` 提供足夠資料計算所有指標

**現價取得方式（盤中 vs 收盤）**:
- `ticker.fast_info.last_price` — 最快速，回傳最新成交價（含盤中）
- 若 `fast_info` 失敗，fallback 到 `history.iloc[-1]['Close']`
- 美股推播時段（17:00–04:00）通常為盤後/盤前，`last_price` 已是最新

**Cache TTL**:
- 台股：5 分鐘（現有設定）
- 美股：5 分鐘（一致）
- Cache key 格式：`us_stock:{symbol}:{date}` 避免與台股 key 衝突

---

## 3. 技術指標計算

所有指標使用 pandas/numpy 計算，yfinance 歷史資料已包含 OHLCV：

| 指標 | 計算方法 | 所需歷史長度 |
|------|----------|-------------|
| RSI(14) | EWM gain/loss ratio | 28 日（至少） |
| MACD(12,26,9) | EMA12 - EMA26，signal EMA9 | 35 日（至少） |
| MA20 | rolling(20).mean() | 20 日 |
| MA50 | rolling(50).mean() | 50 日 |
| Bollinger(20,2) | rolling mean ± 2σ | 20 日 |
| Volume Avg20 | rolling(20).mean() | 20 日 |
| 52W H/L | max/min of 6mo history | 依期間 |

**歷史資料長度**：`period='6mo'` ≈ 126 交易日，足夠計算所有指標（MA50 需 50 日）

**指標計算位置**：新增 `src/fastapistock/services/indicators.py`，純函數，
接收 `pd.DataFrame` 回傳 typed dict。與 repository 解耦，方便單元測試。

---

## 4. 時間窗口邏輯

**Decision**: 使用純函數判斷，傳入 `datetime`（已套用 Asia/Taipei 時區）

```python
# 台股：周一~五（weekday 0~4），08:30–14:00
def is_tw_market_window(now: datetime) -> bool:
    if now.weekday() > 4:
        return False
    minutes = now.hour * 60 + now.minute
    return 8 * 60 + 30 <= minutes <= 14 * 60

# 美股：周一~五 17:00+ 或 周二~六 00:00–04:00
def is_us_market_window(now: datetime) -> bool:
    weekday = now.weekday()  # Mon=0, Sun=6
    minutes = now.hour * 60 + now.minute
    if minutes >= 17 * 60:
        return weekday <= 4        # 只有周一~五的晚上才開始
    if minutes <= 4 * 60:
        return 1 <= weekday <= 5   # 周二~六的凌晨（前一晚的延續）
    return False
```

**測試覆蓋**：邊界條件（08:29/08:30、14:00/14:01、16:59/17:00、04:00/04:01）
與周六/周日/周一凌晨必須有單元測試。

---

## 5. Telegram MarkdownV2 格式

**Decision**: 使用 `parse_mode=MarkdownV2`（而非舊版 `Markdown`）

**Rationale**:
- 舊版 Markdown 對特殊字元處理不一致，容易在數字（如 `+2.30`）中出錯
- MarkdownV2 需 escape：`_ * [ ] ( ) ~ > # + - = | { } . !`
- 實作 `_escape_md(text: str) -> str` helper 處理 escape

**Rationale for helper**:
- 動態數值（股價、漲跌幅）包含 `.`、`+`、`-`、`%` 等需 escape 字元
- 集中一個 escape 函數，不在每個 f-string 手動處理

---

## 6. Railway 部署相容性

**Decision**: APScheduler 跑在 FastAPI process 內，不需任何 Railway 額外設定

**Rationale**:
- Railway 執行 `uvicorn` 啟動 FastAPI，`lifespan` 自動觸發 scheduler 啟動
- 單一 instance 無重複推播問題
- `TELEGRAM_USER_ID`、`TW_STOCKS`、`US_STOCKS` 在 Railway 的 Variables 介面設定

**環境變數傳遞**：Railway Variables → 容器環境變數 → `python-dotenv` 讀取
（Railway 容器不需要 `.env` 檔案，直接讀 `os.getenv`）

---

## 7. 錯誤隔離策略

排程 job 的例外不能讓整個 FastAPI crash：

```python
async def push_job() -> None:
    try:
        # fetch + format + send
        ...
    except Exception:
        logger.exception('Scheduled push failed')
        # 不 re-raise，APScheduler 繼續下一次排程
```

Telegram 發送失敗 → log warning，不影響下次排程。
yfinance 抓取失敗 → log error，跳過該支股票，其餘繼續推播。

---

## 8. 所有 NEEDS CLARIFICATION 已解決

| 問題 | 結論 |
|------|------|
| APScheduler 3.x vs 4.x？ | 3.x，穩定且 FastAPI 整合成熟 |
| 美股即時價 vs 收盤價？ | `fast_info.last_price`（最新），fallback 收盤 |
| MarkdownV2 vs 舊 Markdown？ | MarkdownV2，特殊字元 escape 更可預期 |
| Telegram parse_mode？ | MarkdownV2 |
| 指標計算放哪裡？ | 獨立 `indicators.py` service |
| US cache key 衝突？ | prefix 改為 `us_stock:` |
