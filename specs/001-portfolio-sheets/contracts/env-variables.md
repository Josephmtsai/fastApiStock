# Contract: 環境變數

## 新增變數

| 變數名 | 必填 | 預設值 | 範例值 | 說明 |
|--------|------|--------|--------|------|
| `GOOGLE_SHEETS_ID` | 否* | `''` | `1RDRpwuXjHH...` | Google Sheets 試算表 ID，取自 URL 中 `/d/` 後的長字串 |
| `GOOGLE_SHEETS_PORTFOLIO_GID` | 否* | `''` | `1004709448` | 舊版共用持倉分頁 GID（向後相容） |
| `GOOGLE_SHEETS_PORTFOLIO_GID_TW` | 否 | `GOOGLE_SHEETS_PORTFOLIO_GID` | `1004709448` | 台股持倉分頁 GID |
| `GOOGLE_SHEETS_PORTFOLIO_GID_US` | 否 | `''` | `320283463` | 美股持倉分頁 GID（獨立於 TW） |
| `PORTFOLIO_CACHE_TTL` | 否 | `3600` | `7200` | Redis 快取 TTL（秒），建議 1800–7200 |

> \* 若 `GOOGLE_SHEETS_ID` 為空，持倉功能靜默停用（推播正常，持倉區塊不顯示）

## 如何取得值

**GOOGLE_SHEETS_ID**: 從 Google Sheets URL 取得
```
https://docs.google.com/spreadsheets/d/[SHEET_ID]/edit?gid=[GID]
```

**GOOGLE_SHEETS_PORTFOLIO_GID_TW / GOOGLE_SHEETS_PORTFOLIO_GID_US**: 從對應分頁 URL 的 `gid=` 參數取得

## .env 範例

```env
# 既有設定（不變）
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_USER_ID=123456789
TW_STOCKS=0050,2330,2454
US_STOCKS=AAPL,NVDA

# 新增：持倉試算表
GOOGLE_SHEETS_ID=1RDRpwuXjHHU9nr1BYPk_k6fzRO_lnhnmwrBLws3oHjg
GOOGLE_SHEETS_PORTFOLIO_GID=1004709448
GOOGLE_SHEETS_PORTFOLIO_GID_TW=1004709448
GOOGLE_SHEETS_PORTFOLIO_GID_US=320283463
PORTFOLIO_CACHE_TTL=3600
```
