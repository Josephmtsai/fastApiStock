# 研究備忘：美股分析 API + 設定變數抽取

**第 0 階段產出** — 所有待釐清事項已根據 `sample/` 腳本分析完成。

---

## 決策 1：美股 Yahoo Finance API 取得方式

**決策**：美股採用**原生 Yahoo Finance HTTP API**（v7 quote + v8 chart），以 `httpx` 直接呼叫，**不**使用 `yfinance` 函式庫。

**理由**：
Sample 腳本使用 Yahoo v7 `/finance/quote` 端點，其回應包含 `marketState`（PRE / REGULAR / POST / POSTPOST / CLOSED）以及對應的 `preMarketPrice`、`postMarketPrice` 欄位。`yfinance` 函式庫將這些細節封裝掉，無法乾淨地取得盤前/盤後狀態。美股監控的核心需求之一就是正確顯示目前的市場時段與對應價格，因此必須使用原生 API。

**Crumb 生命週期**：
- 伺服器啟動時（`lifespan`）初始化一次 session + crumb
- 將 `(session, crumb)` 儲存為模組層級 singleton，所有請求共用
- 當偵測到 HTTP 401 或 crumb 失效時，自動重新初始化

**考慮過的替代方案**：
- *`yfinance` 用於美股*：較簡單，但無法正確取得盤前/盤後市場狀態，不符需求。
- *Alpha Vantage / Polygon*：需要付費 API Key，超出範疇。

---

## 決策 2：技術指標計算方式

**決策**：將 TA 指標實作於純 Python/numpy/pandas 模組 `services/technical_analysis.py`，**不引入新函式庫**（如 `ta-lib`、`pandas-ta`）。

**理由**：
Sample 已有正確的 RSI、MACD（EWM 參數）、布林通道實作，直接移植進服務層即可。引入新依賴只是為了 7 個我們已有的函式，不符合 YAGNI 原則。同時避免 `ta-lib` 的 C 擴充套件在 Railway 上的編譯問題。

**考慮過的替代方案**：
- *`pandas-ta`*：增加一個依賴只用 7 個函式，過度引入。
- *`ta-lib`*：C 擴充套件，Railway 部署需要額外編譯環境。

---

## 決策 3：Yahoo Session Singleton

**決策**：在 `repositories/us_stock_repo.py` 以模組層級變數儲存 `_yahoo_session: requests.Session | None` 與 `_yahoo_crumb: str | None`，在 FastAPI `lifespan` 中初始化。

**理由**：
Yahoo Finance 需要兩步驟握手（取得 cookie + crumb），每次請求都重新初始化會增加 200–500ms 延遲。單次初始化符合 sample 的設計，也符合 constitution IV 的效能要求。

**注意**：`requests.Session` 為同步；從 async route handler 呼叫時須透過 `run_in_executor` 包裝（與現有 `twstock_repo` 使用 `yfinance` 的模式相同）。

---

## 決策 4：Google Sheets 整合方式

**決策**：以 `httpx` GET 請求直接抓取公開 Google Sheets CSV export，設定 15s timeout，**不**使用 Google Sheets API 用戶端函式庫，**不需** OAuth。

**理由**：
Sample 使用 `https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}` 端點，對所有設定為「任何人皆可檢視」的試算表有效。`httpx` GET 與專案現有 HTTP 模式一致，無需額外認證設定。

**快取策略**：
Google Sheets 資料以 Redis 快取，TTL 由 `GS_CACHE_TTL` env var 控制（預設 300s），避免頻繁抓取試算表。

**考慮過的替代方案**：
- *Google Sheets API v4（gspread）*：需要 OAuth / 服務帳號，對唯讀公開試算表來說過度複雜。

---

## 決策 5：需抽取至設定檔的變數清單

以下為所有需從 sample 腳本移出的硬編碼值：

| 原始位置 | 硬編碼值 | 新設定 Key |
|---------|---------|-----------|
| `sample/stock_check.py` | `TELEGRAM_TOKEN = "8141..."` | `TELEGRAM_TOKEN`（已在 config.py，確認無誤） |
| `sample/stock_check.py` | `TELEGRAM_CHAT_ID = "6696..."` | `TELEGRAM_CHAT_ID`（新增至 config.py） |
| `sample/stock_check.py` | `SYMBOLS = ["VOO",...]` | `US_STOCK_SYMBOLS` env var |
| `sample/ft_monitor.py` | `SHEET_ID = "1RDR..."` | `GOOGLE_SHEET_ID` env var |
| `sample/ft_monitor.py` | `SHEET_GID = "3202..."` | `GOOGLE_SHEET_FT_GID` env var |
| `sample/ft_monitor.py` | `QUARTERLY_GID = "1192..."` | `GOOGLE_SHEET_QUARTERLY_GID` env var |
| `sample/ft_monitor.py` | `WATCH_SYMBOLS = [...]` | `FT_WATCH_SYMBOLS` env var |
| `sample/ft_monitor.py` | `5%` / `10%` 跌幅門檻 | `FT_ALERT_BELOW_PCT_WARN=5`、`FT_ALERT_BELOW_PCT_CRITICAL=10` |
| `sample/ft_monitor.py` | `20%` 回落門檻 | `FT_ALERT_DROP_FROM_HIGH_PCT=20` |
| `src/.../stock_service.py` | `_CACHE_TTL = 5` | `TW_STOCK_CACHE_TTL=5` |
| 新程式碼 | 美股快取 TTL | `US_STOCK_CACHE_TTL=60` |
| 新程式碼 | Google Sheets 快取 TTL | `GS_CACHE_TTL=300` |

**不需移出的值**：
- `TICKER_MAP`（Google Finance → Yahoo 代碼對照）：非機密常數，直接定義在 `google_sheets_repo.py` 中。
- `YAHOO_HEADERS`（User-Agent 字串）：非機密，定義為模組常數即可。

---

## 決策 6：路由結構

**決策**：
- `GET /api/v1/us-stock/{symbol}` — 單一股票查詢
- `GET /api/v1/us-stock` + query param `?symbols=VOO,QQQ,NVDA` — 批次查詢（與台股路由模式一致）
- `GET /api/v1/ft-monitor` — 持倉警示 + 季度摘要

**理由**：與現有台股路由慣例完全一致，符合 constitution III 的 API 一致性原則。

---

## 已解決事項彙整

| 問題 | 決策 |
|------|------|
| yfinance vs 原生 Yahoo API | 美股使用原生 Yahoo HTTP（支援盤前/盤後） |
| TA 函式庫 | 移植 sample 程式碼至 `services/technical_analysis.py`，不新增依賴 |
| Yahoo crumb 生命週期 | 模組 singleton，在 lifespan 初始化，失效時自動重試 |
| Google Sheets 認證 | 公開 CSV export via httpx，不需 OAuth |
| Google Sheets 快取 | Redis + `GS_CACHE_TTL` env var |
| 硬編碼機密 | 全部移至 config.py + .env；TICKER_MAP 保留為常數 |
| `sample/` 腳本 | 僅供參考；不被生產套件 import |
| `_CACHE_TTL` 台股 | 抽取至 `TW_STOCK_CACHE_TTL` env var |
