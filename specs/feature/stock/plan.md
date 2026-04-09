# 實作計畫：美股分析 API + 設定變數抽取

**分支**：`feature/stock` | **日期**：2026-04-06 | **規格**：`specs/feature/stock/spec.md`

---

## 摘要

從 `sample/stock_check.py` 與 `sample/ft_monitor.py` 兩支腳本萃取邏輯，整合進現有 FastAPI 架構，新增三大功能：

1. **美股報價 + 技術分析 API**（P1）：`GET /api/v1/us-stock/{symbol}` 與批次查詢，使用原生 Yahoo Finance HTTP + Redis 快取。
2. **FT 持倉監控 API**（P2）：`GET /api/v1/ft-monitor`，讀取 Google Sheets 持倉資料，判斷買入警示與季度進度。
3. **設定變數抽取**（P3）：所有 sample 腳本的硬編碼機密與數值全數移至 `.env`；`_CACHE_TTL` 等台股魔法數字也一併抽取。

現有 `twstock_repo.py`、`stock_service.py`、`telegram_service.py` **不做改動**（除了 `_CACHE_TTL` → config）。

---

## 技術背景

| 項目 | 內容 |
|------|------|
| 語言版本 | Python 3.11+ |
| 主要依賴 | FastAPI、httpx（美股/Google Sheets 用）、redis-py、numpy、pandas |
| 新依賴 | 無（不引入 ta-lib / pandas-ta） |
| 儲存 | Redis（現有架構；美股與 FT Monitor 新增 key） |
| 測試 | pytest + fakeredis（現有模式） |
| 目標平台 | Railway（單一 uvicorn 進程） |
| 效能目標 | Redis 快取命中 < 200ms；live fetch < 3s |
| 限制 | Yahoo crumb session 為 singleton；不阻塞 event loop |

---

## Constitution 合規性檢查

| 原則 | 狀態 | 說明 |
|------|------|------|
| I. 程式碼品質 | 通過 | 全新程式碼加型別標記、docstring、ruff + mypy |
| II. 測試標準 | 通過 | 美股、FT Monitor、TA 模組均建立測試 |
| III. API 一致性 | 通過 | 所有回應使用 `ResponseEnvelope`；新路由透過 `APIRouter` |
| IV. 效能與韌性 | 通過 | run_in_executor 包裝同步 HTTP；Redis 快取；graceful degradation |
| V. 可觀測性 | 通過 | `LoggingMiddleware` 自動涵蓋所有新路由 |

**無違規。**

---

## 專案結構

### 文件（本功能）

```text
specs/feature/stock/
├── plan.md              ← 本文件
├── spec.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── us_stock_api.md
│   └── ft_monitor_api.md
└── tasks.md             ← 由 /speckit-tasks 產生
```

### 原始碼異動

```text
src/fastapistock/
├── main.py                              修改 — 新增路由、限流豁免設定
├── config.py                            修改 — 新增美股/FT/Google Sheets 設定變數
├── schemas/
│   ├── us_stock.py                      新增 — TechnicalAnalysis, SentimentScore, USStockData
│   └── ft_monitor.py                    新增 — FTAlert, FTHolding, QuarterlySummary, FTMonitorResult
├── services/
│   ├── stock_service.py                 修改 — _CACHE_TTL 改讀 TW_STOCK_CACHE_TTL config
│   ├── technical_analysis.py            新增 — calc_rsi, calc_macd, calc_bollinger, calc_ta, sentiment_score
│   ├── us_stock_service.py              新增 — get_us_stock(), get_us_stocks() + Redis 快取
│   └── ft_monitor_service.py            新增 — 整合 Google Sheets + 美股報價 + 警示邏輯
├── repositories/
│   ├── us_stock_repo.py                 新增 — Yahoo crumb session singleton + v7/v8 API
│   └── google_sheets_repo.py            新增 — CSV export fetch, TICKER_MAP 常數
└── routers/
    ├── us_stocks.py                     新增 — GET /api/v1/us-stock/{symbol} 與批次查詢
    └── ft_monitor.py                    新增 — GET /api/v1/ft-monitor

tests/
├── test_us_stock.py                     新增 — 報價、快取、TA、情緒評分測試
├── test_ft_monitor.py                   新增 — Google Sheets 解析、警示邏輯、快取降級測試
└── test_technical_analysis.py           新增 — RSI/MACD/BB 計算單元測試

.env.example                             修改 — 補充所有新增變數
```

---

## 實作階段

### 階段 1 — Config 擴充 + Schema 定義（無副作用，可獨立合併）

1. **`config.py`**：新增 `_csv_list` 輔助函式；加入所有美股、FT Monitor、Google Sheets 設定變數；將 `TELEGRAM_CHAT_ID` 從 sample 硬編碼移入。
2. **`stock_service.py`**：將 `_CACHE_TTL = 5` 改為讀取 `config.TW_STOCK_CACHE_TTL`。
3. **`schemas/us_stock.py`**：定義 `TechnicalAnalysis`、`SentimentScore`、`USStockData`。
4. **`schemas/ft_monitor.py`**：定義 `FTAlert`、`FTHolding`、`QuarterlyProgress`、`QuarterlySummary`、`FTMonitorResult`。
5. **`.env.example`**：補充所有新增 key 及說明。

### 階段 2 — 技術分析服務（純計算，無 I/O）

6. **`services/technical_analysis.py`**：
   - 移植 `calc_rsi(series, window=14)`
   - 移植 `calc_macd(series, fast=12, slow=26, signal=9)`
   - 移植 `calc_bollinger(series, window=20, num_std=2)`
   - 移植 `calc_ta(df, current_price) -> TechnicalAnalysis`
   - 移植 `sentiment_score(symbol, price, change_pct, ta) -> SentimentScore`（原 `claude_analysis`，重命名）

7. **`tests/test_technical_analysis.py`**：使用固定的 pandas DataFrame 驗證 RSI/MACD/BB 數值正確性。

### 階段 3 — 美股 Repository + Service + Router（P1 核心）

8. **`repositories/us_stock_repo.py`**：
   - `_yahoo_session`、`_yahoo_crumb` 模組 singleton
   - `init_yahoo_session() -> None`：取得 cookie + crumb
   - `fetch_us_quote(symbols: list[str]) -> dict[str, dict]`：v7 批次報價
   - `fetch_us_history(symbol: str, period: str) -> pd.DataFrame`：v8 歷史資料
   - `fetch_us_stock(symbol: str) -> USStockData`：完整單支資料抓取（sleep + quote + history + TA + sentiment）

9. **`services/us_stock_service.py`**：
   - `get_us_stock(symbol: str) -> USStockData`：Redis 快取優先
   - `get_us_stocks(symbols: list[str]) -> list[USStockData]`：ThreadPoolExecutor 並行

10. **`routers/us_stocks.py`**：
    - `GET /api/v1/us-stock/{symbol}`
    - `GET /api/v1/us-stock?symbols=VOO,QQQ`

11. **`main.py`**：在 `lifespan` 加入 `init_yahoo_session()` 呼叫（非阻塞式 executor）；注冊 `us_stocks.router`；在限流設定中新增 `RATE_LIMIT_US_STOCK_*`。

12. **`tests/test_us_stock.py`**：mock Yahoo HTTP 呼叫，測試快取行為、404、503 降級。

### 階段 4 — FT Monitor Repository + Service + Router（P2）

13. **`repositories/google_sheets_repo.py`**：
    - `TICKER_MAP` 硬編碼常數
    - `fetch_ft_summary() -> dict[str, FTHolding]`：從 `GOOGLE_SHEET_FT_GID` 抓 CSV
    - `fetch_quarterly_data() -> tuple[dict, date | None, date | None]`：從 `QUARTERLY_GID` 抓 CSV

14. **`services/ft_monitor_service.py`**：
    - `get_ft_monitor_result() -> FTMonitorResult`：整合 Google Sheets + us_stock_service + 警示邏輯
    - `check_alerts(symbol, price, holding, w52h) -> list[FTAlert]`：條件判斷（閾值讀自 config）

15. **`routers/ft_monitor.py`**：`GET /api/v1/ft-monitor`

16. **`main.py`**：注冊 `ft_monitor.router`；新增 `RATE_LIMIT_FT_MONITOR_*` 限流設定。

17. **`tests/test_ft_monitor.py`**：mock httpx + Google Sheets CSV，測試警示邏輯與快取降級。

---

## 關鍵現有檔案（重用，不改動邏輯）

| 檔案 | 用途 |
|------|------|
| `src/fastapistock/services/stock_service.py` | `get_stocks()` — 台股查詢不動 |
| `src/fastapistock/services/telegram_service.py` | `send_stock_message()` — 可被排程器重用 |
| `src/fastapistock/middleware/logging.py` | 自動涵蓋所有新路由，無需修改 |
| `src/fastapistock/middleware/rate_limit/` | 新路由的限流設定透過 env var 加入 |
| `tests/conftest.py` | `fakeredis` fixture — 新測試直接沿用 |
| `src/fastapistock/cache/redis_cache.py` | `put()` / `get()` — 新 service 直接呼叫 |

---

## 驗證步驟

```bash
# 1. 靜態檢查
uv run ruff check . --fix && uv run ruff format .
uv run mypy src/

# 2. 全部測試
uv run pytest -q

# 3. 手動驗證美股 API
curl http://localhost:8000/api/v1/us-stock/NVDA
curl "http://localhost:8000/api/v1/us-stock?symbols=VOO,QQQ"

# 4. 手動驗證 FT Monitor
curl http://localhost:8000/api/v1/ft-monitor

# 5. 確認機密值已清除
grep -rn '8141247468\|6696169593\|1RDRpwuXjHHU9nr1BYPk_k6fzRO_lnhnmwrBLws3oHjg' sample/ src/
# 預期：零比對
```
