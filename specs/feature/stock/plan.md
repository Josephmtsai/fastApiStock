# Implementation Plan：定時股票推播排程 + 手動觸發 API

**Branch**: `feature/stock` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/feature/stock/spec.md`

## Summary

在 FastAPI lifespan 中啟動 APScheduler AsyncIOScheduler，每 30 分鐘依照 Asia/Taipei
時區時間窗口自動推播股票技術分析。同時：升級現有 `/api/v1/tgMessage/{id}` 為富格式
MarkdownV2 訊息；新增 `/api/v1/usMessage/{id}` 支援美股手動查詢。
排程器與 API endpoint 共用同一套 service 層，不重複實作。

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: FastAPI, APScheduler 3.x, yfinance, redis-py, httpx, pandas, numpy
**Storage**: Redis（快取，TTL=5 min）；無資料庫
**Testing**: pytest + fakeredis + unittest.mock（mock yfinance）
**Target Platform**: Railway（單一 Linux container）
**Project Type**: Web service + 排程背景任務
**Performance Goals**: 排程 job < 30 s；API endpoint p95 < 2 s（cache miss）
**Constraints**: Telegram 訊息 < 4096 字元；yfinance timeout = 10 s；Telegram timeout = 10 s
**Scale/Scope**: 單一用戶；3–5 支台股 + 3–5 支美股

## Constitution Check

### 初始評估（Phase 0 前）

| 原則 | 狀態 | 說明 |
|------|------|------|
| I. Code Quality | ✅ PASS | 所有設定由 `.env` 讀取；無 print()；型別標記完整；magic numbers 進 config |
| II. Testing | ✅ PASS | 時間窗口邏輯（12 邊界案例）、指標計算、formatter、endpoint 均有測試 |
| III. API Consistency | ✅ PASS | 新 endpoint 遵循 envelope；現有 API 介面不破壞 |
| IV. Performance | ✅ PASS | US/TW rich stocks 皆走 Redis cache；timeout 設定；並行抓取 |
| V. Observability | ✅ PASS | 排程觸發/完成/失敗均 logging；API 走現有 LoggingMiddleware |

**Security**: TELEGRAM_USER_ID、TELEGRAM_TOKEN 由 env 讀取；ticker 輸入過濾

### 複查（Phase 1 設計後）

| 原則 | 狀態 | 說明 |
|------|------|------|
| I. Code Quality | ✅ PASS | RichStockData、IndicatorResult 完整型別；`_escape_md` 集中處理 MarkdownV2 |
| II. Testing | ✅ PASS | `test_us_telegram.py` 覆蓋 /api/v1/usMessage；邊界條件列於 quickstart |
| III. API Consistency | ✅ PASS | `us_telegram.py` router 使用 APIRouter prefix；envelope 格式一致 |
| IV. Performance | ✅ PASS | cache key `rich_tw:` / `us_stock:` 不衝突；共用 Redis instance |
| V. Observability | ✅ PASS | push job 有 try/except + logger.exception；不 re-raise |

**無 Constitution 違規。**

## Project Structure

### Documentation (this feature)

```text
specs/feature/stock/
├── plan.md                              # 本文件
├── spec.md                              # 功能規格
├── research.md                          # Phase 0 研究結論
├── data-model.md                        # Phase 1 資料模型
├── quickstart.md                        # 快速上手指南
├── contracts/
│   ├── env-variables.md                 # 環境變數合約
│   ├── telegram-message-format.md       # Telegram MarkdownV2 格式規範
│   └── api-endpoints.md                 # API endpoint 合約（新增）
└── tasks.md                             # Phase 2（/speckit.tasks 產生）
```

### Source Code

```text
src/fastapistock/
├── config.py              # 新增：TELEGRAM_USER_ID, tw_stock_codes(), us_stock_symbols()
├── main.py                # 修改：新增 lifespan + include us_telegram router
├── scheduler.py           # 新增：排程邏輯、時間窗口判斷、build_scheduler()
├── schemas/
│   └── stock.py           # 新增：RichStockData（現有 StockData 不動）
├── repositories/
│   ├── twstock_repo.py    # 新增：fetch_tw_rich_stock()（現有 fetch_stock() 不動）
│   └── us_stock_repo.py   # 新增：fetch_us_stock()
├── services/
│   ├── indicators.py      # 新增：calculate() + score_stock()（RSI/MACD/MA/BB/評分）
│   ├── stock_service.py   # 新增：get_rich_tw_stock/s()（現有函式不動）
│   ├── us_stock_service.py # 新增：get_us_stock/s()
│   ├── scheduler_push.py  # 新增：push_tw_stocks(), push_us_stocks()
│   └── telegram_service.py # 新增：format_rich_stock_message(), send_rich_stock_message()
└── routers/
    ├── telegram.py        # 修改：改呼叫 get_rich_tw_stocks + send_rich_stock_message
    └── us_telegram.py     # 新增：GET /api/v1/usMessage/{id}

tests/
├── test_scheduler.py         # 新增：12 個時間窗口邊界條件
├── test_indicators.py        # 新增：技術指標計算
├── test_us_stock_repo.py     # 新增：美股 repo（mock yfinance）
├── test_telegram_formatter.py # 新增：MarkdownV2 格式化
├── test_us_telegram.py       # 新增：/api/v1/usMessage endpoint
└── ...（現有測試不動）
```

**Structure Decision**: 沿用現有 Option 1（單一專案），新模組放入現有目錄。

### 共用 Service 呼叫關係

```
手動 API                        排程器
GET /api/v1/tgMessage          _scheduled_push()
GET /api/v1/usMessage                │
        │                            │
        ▼                            ▼
  get_rich_tw_stocks()     get_rich_tw_stocks()   ← 同一函式
  get_us_stocks()          get_us_stocks()         ← 同一函式
        │
        ▼
  send_rich_stock_message()
  format_rich_stock_message()  → MarkdownV2
  httpx.post(Telegram API)
```

## Complexity Tracking

> 無 Constitution 違規，此節不需填寫。
