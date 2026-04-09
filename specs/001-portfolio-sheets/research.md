# Research: Google Sheets 持倉整合

**Branch**: `001-portfolio-sheets` | **Date**: 2026-04-09

## 決策 1：Google Sheets 讀取方式

**Decision**: 使用 CSV export URL（無需認證）

```
https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}
```

**Rationale**:
- 試算表已設為公開分享，CSV 匯出 URL 直接可存取，不需 API 金鑰或 OAuth token
- 使用專案現有的 `httpx` 發送 GET 請求，零新依賴
- CSV 格式由 Python 標準函式庫 `csv` 解析，無需額外套件

**Alternatives considered**:
- `gspread` + Service Account JSON：需申請 Google Cloud Project、建立 Service Account、管理 JSON key 檔案 → 過度複雜，違反 KISS 原則
- Google Sheets API v4 via `httpx`：需 OAuth，公開試算表不需要

---

## 決策 2：欄位索引設計

**Decision**: 欄位索引定義為模組層級具名常數（非 env var）

```python
_COL_SYMBOL = 0       # A欄：代號
_COL_SHARES = 2       # C欄：持股數
_COL_AVG_COST = 5     # F欄：平均成本
_COL_UNREALIZED_PNL = 8  # I欄：未實現損益
```

**Rationale**:
- 欄位結構與特定試算表版型綁定，若欄位位置改變，程式邏輯也需重測 → 非純設定值
- Constitution §I 要求「configuration values MUST be externalised」，但欄位索引屬於「structural constant」非「deployment config」
- 具名常數（非 magic number）已滿足 constitution 的可維護性要求
- 若未來真的需要彈性，可升級為 env var（無破壞性變更）

**Alternatives considered**:
- 全部 env var（`PORTFOLIO_COL_SYMBOL=0`）：過度設計，YAGNI

---

## 決策 3：快取設計

**Decision**: 單一 Redis key `portfolio:tw`，TTL 由 `PORTFOLIO_CACHE_TTL` env var 控制（預設 3600 秒）

**Rationale**:
- 持倉資料在一個 TTL 週期內不會改變（日常交易頻率遠低於 1 小時）
- 單一 key 比 per-symbol key 更簡單，且 Portfolio 整體更新的語義更清晰
- TTL 設為 env var 符合 constitution §I（configuration value 外部化）
- 降級：Redis 不可用時直接抓取（constitution §IV graceful fallback）

**Cache key format**:
```
portfolio:tw  →  dict[symbol, {shares, avg_cost, unrealized_pnl}]
```

**Note**: 不加日期 suffix（與 rich_tw 不同），因 TTL 本身就是時效控制，Portfolio 以 TTL expiry 為更新機制。

---

## 決策 4：持倉合併位置（Service Layer）

**Decision**: 在 `get_rich_tw_stocks()` 末端合併持倉資料（service 層，非 router 層）

**Rationale**:
- 定時排程（`push_tw_stocks()`）和手動 API（`GET /api/v1/tgMessage`）都呼叫 `get_rich_tw_stocks()`，合併一次即可覆蓋兩個路徑
- 符合 constitution §III：「Business logic MUST NOT be placed in route handlers」
- `_merge_portfolio()` 為純函式（list + dict → list），易於單元測試

**Flow**:
```
get_rich_tw_stocks(codes)
  ├── cache lookup / yfinance fetch → list[RichStockData]
  ├── _get_cached_portfolio() → dict[symbol, PortfolioEntry]
  └── _merge_portfolio(stocks, portfolio) → list[RichStockData]
```

---

## 決策 5：Telegram 顯示格式

**Decision**: 在漲跌行之後、RSI 行之前插入「持倉」區塊（僅持有時顯示）

```
🔺 *2330* 台積電
   現價: `895.00 TWD`   昨收: `885.00`
   漲跌: `+10.00` (+1.13%)
   ─── 持倉 ───
   持股: `1,000`   成本: `820.00` (+9.15%)
   損益: `+75,000 TWD`
   RSI(14): `62.3`
   均線: `MA20:880↑  MA50:850↑`
   ...
```

**Rationale**:
- 持倉資訊與「現價」最相關，緊接在漲跌行後最符合閱讀流程
- 損益與成本直接呈現，不需再計算
- `─── 持倉 ───` 分隔線視覺區分技術分析與個人資料

---

## 技術風險評估

| 風險 | 可能性 | 因應 |
|------|--------|------|
| Google Sheets 速率限制 | 低（1小時快取） | Redis TTL 隔離 |
| 試算表設為非公開 | 低（用戶自控） | HTTP 4xx → log warning，graceful return {} |
| CSV 格式變更（千分位、負號） | 中 | `_parse_number()` 統一 strip + replace |
| Redis 不可用 | 低 | 直接 fetch（constitution §IV 降級要求） |
