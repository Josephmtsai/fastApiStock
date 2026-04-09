# 功能規格：美股分析 API + 設定變數抽取

**功能分支**：`feature/stock`
**建立日期**：2026-04-06
**狀態**：草稿（符合 constitution v1.2.0）
**需求來源**：整合 `sample/stock_check.py` 與 `sample/ft_monitor.py`；建立美股分析 API；將所有硬編碼變數移至設定檔

**規範依據**：所有規則須與 [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) 保持一致，如有衝突以 constitution 為準。

---

## 背景說明

### `sample/stock_check.py` 現有功能

- 以 Yahoo Finance v7 API（原生 HTTP + crumb 驗證）抓取 VOO、QQQ、NVDA、TSM 等美股即時報價
- 支援盤前 / 盤中 / 盤後三種市場狀態（依 Yahoo `marketState` 欄位判斷）
- 計算技術指標：RSI(14)、MACD(12/26/9)、MA20/50/200、布林通道(20,2σ)、成交量比、52週高低點
- 規則評分系統（分數 −8..+8）→ 判斷「看漲 / 中性觀望 / 看跌」
- 傳送格式化 Telegram 報告

### `sample/ft_monitor.py` 現有功能

- 從 Google Sheets 讀取持倉資料（均價、股數、最高買入價）
- 觸發買入提醒：現價低於均價 5% 或 10%
- 觸發回調提醒：現價高於均價，但距最高點回落超過 20%
- 讀取季度購買目標進度表，顯示達成率
- 傳送格式化 Telegram 提醒

### ⚠️ 問題：硬編碼敏感資訊

兩支腳本皆有**硬編碼的機密值**（`TELEGRAM_TOKEN`、`TELEGRAM_CHAT_ID`、`SHEET_ID`、`SHEET_GID`），
**必須**全部移至 `.env`，符合 constitution 第 I 原則。

---

## 使用者情境與測試 *(必填)*

### 使用者故事 1 — 美股報價 + 技術分析 API（優先級：P1）

客戶端呼叫 `GET /api/v1/us-stock/{symbol}`，取得即時報價（含盤前/盤後）、完整技術指標與情緒評分，格式與現有台股 API 完全一致。

**為何優先**：可獨立運作，不依賴 Google Sheets，直接重用現有快取與限流架構，風險最低。

**獨立測試**：`GET /api/v1/us-stock/NVDA` → 200，回應包含 `price`、`market_state`、`ta`（含 RSI/MACD/MA/BB）、`sentiment`（含 `verdict`/`score`）。

**驗收情境**：

1. **給定**有效的美股代碼（如 `NVDA`），**當**呼叫 `GET /api/v1/us-stock/NVDA`，**則**回應包含 `price`、`prev_close`、`change_pct`、`market_state` 及 `ta` 物件。

2. **給定**同一代碼在 `US_STOCK_CACHE_TTL` 秒內被呼叫兩次，**當**第二次請求到達，**則**不發出 Yahoo Finance HTTP 呼叫（Redis 快取命中），回應時間 < 200ms。

3. **給定** Yahoo Finance 暫時無法連線，**當**快取為空時發出請求，**則** API 回傳 503（不掛死；遵守 timeout 設定）。

4. **給定**不存在的代碼（如 `ZZZZ`），**當**呼叫 `GET /api/v1/us-stock/ZZZZ`，**則** API 回傳 404，`{"status":"error","message":"Symbol ZZZZ not found"}`。

---

### 使用者故事 2 — FT 持倉監控 API（優先級：P2）

客戶端呼叫 `GET /api/v1/ft-monitor`，取得持倉警示狀態（是否低於均價閾值、是否距高點回落）及季度購買進度，不需手動執行腳本。

**為何優先**：依賴 US1 的即時報價；Google Sheets 整合增加外部依賴複雜度，故排 P2。

**獨立測試**：`GET /api/v1/ft-monitor` → 200，回應包含 `alerts` 清單與 `quarterly_summary`。Google Sheets 無法存取時回傳 503（不崩潰）。

**驗收情境**：

1. **給定** Google Sheets 可存取且持倉資料正確，**當**呼叫 `GET /api/v1/ft-monitor`，**則**回應包含 `holdings`、`alerts`、`quarterly_summary`。

2. **給定**某持倉現價低於均價 10% 以上，**當**呼叫，**則** `alerts` 中出現 `type: BELOW_AVG_10` 並附帶買入建議。

3. **給定** Google Sheets 回傳錯誤或逾時，**當**呼叫，**則** API 回傳 503 並附帶說明訊息，不崩潰。

4. **給定**所有持倉均在正常範圍，**當**呼叫，**則** `alerts` 為空列表，`status` 為 `success`。

---

### 使用者故事 3 — 設定變數抽取（優先級：P3）

將 `sample/` 腳本及 `src/` 中所有硬編碼的值（機密、門檻、URL、符號清單）全數移至 `config.py` / `.env` / `.env.example`，符合 constitution 第 I 原則。

**為何優先**：不阻擋 US1/US2 開發，但為合規必要項目。

**獨立測試**：`grep -rn '8141247468\|6696169593\|1RDRpwuXjHHU9nr1BYPk_k6fzRO_lnhnmwrBLws3oHjg' sample/ src/` → 零比對結果。

**驗收情境**：

1. **給定**重構後的程式碼，**當**執行上方 grep，**則**找不到任何硬編碼的機密值。

2. **給定** `.env.example`，**當**新開發者閱讀，**則**所有必要變數（Telegram、Google Sheets IDs、閾值）都有說明與佔位符。

---

### 邊界案例

- **盤前/盤後**：Yahoo `marketState` 決定顯示哪個價格欄位，`market_state` 與 `price_label` 必須保留在 API 回應中。
- **歷史資料不足**：MA200 需要 200 筆資料；不足時對應欄位回傳 `null` 而非報錯。
- **Google Sheets 無法存取（ft-monitor）**：若 Redis 有舊資料則回傳舊資料；否則回傳 503。
- **Yahoo 限流**：美股 repo 同樣需要隨機延遲（constitution IV）。
- **台股 vs 美股代碼**：美股代碼為純英文字母（VOO、NVDA）；台股代碼為數字（0050）。各自使用獨立 Router，互不干擾。

---

## 功能需求 *(必填)*

- **FR-001**：`GET /api/v1/us-stock/{symbol}` 回傳報價、漲跌、市場狀態、完整 TA、情緒評分。
- **FR-002**：美股資料必須以 Redis 快取，TTL 由 `US_STOCK_CACHE_TTL` 控制。
- **FR-003**：Yahoo Finance session（crumb）在伺服器啟動時初始化一次並重複使用；crumb 失效時自動重新初始化。
- **FR-004**：技術指標計算（RSI、MACD、MA、BB、成交量、52週）必須放在獨立的 `services/technical_analysis.py` 模組，不得內嵌於 repository 或 route handler。
- **FR-005**：`GET /api/v1/ft-monitor` 透過獨立的 repository 讀取 Google Sheets，業務邏輯放在 `ft_monitor_service.py`。
- **FR-006**：警示閾值（5%、10%、20%）必須透過 `FT_ALERT_BELOW_PCT_WARN`、`FT_ALERT_BELOW_PCT_CRITICAL`、`FT_ALERT_DROP_FROM_HIGH_PCT` env var 設定。
- **FR-007**：`sample/` 與 `src/` 中所有硬編碼的 Token、ID、閾值必須移至 `config.py`。
- **FR-008**：兩條新路由均須納入限流設定，使用 per-route env var 配置。
- **FR-009**：Google Sheets 請求必須設定 timeout（constitution IV）；失敗時優雅降級。
- **FR-010**：支援批次查詢 `GET /api/v1/us-stock?symbols=VOO,QQQ`（與台股 pattern 一致）。

---

## 成功標準 *(必填)*

- **SC-001**：`GET /api/v1/us-stock/NVDA` 回傳含完整 TA 與情緒評分的 200 回應。
- **SC-002**：`GET /api/v1/ft-monitor` 回傳持倉警示與季度進度的 200 回應。
- **SC-003**：`uv run pytest` 通過，新模組覆蓋率 ≥ 80%。
- **SC-004**：`uv run mypy src/` 結束碼為 0。
- **SC-005**：機密 grep 測試（SC-003 情境 1）零比對。

---

## 假設前提

- Yahoo Finance v7 API 的 crumb 方式比 `yfinance` 更能正確支援盤前/盤後市場狀態。
- 台股繼續使用 `yfinance`（現有架構不變）。
- Google Sheets 文件為公開閱讀（CSV export 不需 OAuth）。
- `TICKER_MAP`（Google Finance → Yahoo 代碼對照表）為硬編碼常數，非機密，無需移至 env。
- `sample/` 資料夾腳本僅作參考；**不**被生產套件 import。
