# Contract：環境變數設定

## 現有變數（不變）

| 變數名稱 | 型別 | 說明 | 必填 |
|----------|------|------|------|
| `REDIS_HOST` | string | Redis 主機位址 | 否（預設 `localhost`） |
| `REDIS_PORT` | int | Redis 連接埠 | 否（預設 `6379`） |
| `REDIS_PASSWORD` | string | Redis 密碼 | 否 |
| `TELEGRAM_TOKEN` | string | Telegram Bot API Token | 是 |

## 新增變數

| 變數名稱 | 型別 | 說明 | 必填 | 範例 |
|----------|------|------|------|------|
| `TELEGRAM_USER_ID` | string | 接收推播的 Telegram chat/user ID | 是 | `123456789` |
| `TW_STOCKS` | string | 台股代碼，逗號分隔 | 是 | `0050,2330,2454` |
| `US_STOCKS` | string | 美股代碼，逗號分隔 | 是 | `AAPL,TSLA,NVDA` |

## 驗證規則

- `TELEGRAM_USER_ID`：非空字串，應為純數字（Telegram chat ID）
- `TW_STOCKS`：逗號分隔的台股代碼，每個代碼應為數字字串（如 `0050`）
- `US_STOCKS`：逗號分隔的美股 ticker，大小寫不敏感（自動轉大寫）
- 若 `TW_STOCKS` 或 `US_STOCKS` 為空，對應市場的排程 job 會 log warning 並跳過

## Railway 部署設定方式

在 Railway 介面的 `Variables` 頁面加入上述變數。
Railway 會自動注入為容器環境變數，`python-dotenv` 透過 `os.getenv()` 讀取，
**不需要** `.env` 檔案存在於容器中。

## 本地開發 .env 範例

```env
# Redis（Railway 提供 Redis plugin 時會自動設定 REDIS_URL，需手動拆分）
REDIS_HOST=localhost
REDIS_PORT=6379

# Telegram
TELEGRAM_TOKEN=8141247468:AAXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
TELEGRAM_USER_ID=6696169593

# 股票清單
TW_STOCKS=0050,2330,2454
US_STOCKS=AAPL,TSLA,NVDA
```

> **注意**：`.env` 檔案已在 `.gitignore` 中，不應 commit 到版控。
