# Quickstart：定時股票推播排程

## 本地開發環境

### 前置條件

- Python 3.11+（透過 `.python-version`）
- UV 套件管理器
- Redis 執行中（localhost:6379）
- Telegram Bot Token 與 User ID

### 1. 安裝新依賴

```bash
uv add "apscheduler>=3.10,<4"
```

### 2. 設定 .env

```bash
cp .env.example .env
# 填入以下值：
```

```env
REDIS_HOST=localhost
REDIS_PORT=6379

TELEGRAM_TOKEN=your_bot_token_here
TELEGRAM_USER_ID=your_chat_id_here

TW_STOCKS=0050,2330
US_STOCKS=AAPL,NVDA
```

> 如何取得 Telegram User ID：對話 `@userinfobot`，它會回傳你的 ID。

### 3. 啟動服務

```bash
uv run uvicorn fastapistock.main:app --reload
```

啟動後 log 會顯示：
```
INFO  fastapistock.main APScheduler started
INFO  apscheduler.scheduler Scheduler started
```

### 4. 驗證排程設定

```bash
# 查看 APScheduler 是否正常啟動
curl http://localhost:8000/health
```

### 5. 手動觸發測試推播

排程器在時間窗口外不發送，本地測試可直接呼叫 API endpoint：

```bash
# 台股手動推播（升級為富格式 MarkdownV2）
curl "http://localhost:8000/api/v1/tgMessage/YOUR_CHAT_ID?stock=0050,2330"

# 美股手動推播（新 endpoint）
curl "http://localhost:8000/api/v1/usMessage/YOUR_CHAT_ID?stock=AAPL,NVDA,TSM"

# 確認 OpenAPI 文件
open http://localhost:8000/docs
```

**YOUR_CHAT_ID** 即 `.env` 中的 `TELEGRAM_USER_ID`。

---

## Railway 部署

### 1. 設定 Variables

在 Railway 專案 → Service → Variables：

```
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_USER_ID=your_chat_id
TW_STOCKS=0050,2330,2454
US_STOCKS=AAPL,TSLA,NVDA
```

Redis 相關變數 Railway 的 Redis plugin 會自動注入，
若手動設定請確認 `REDIS_HOST`、`REDIS_PORT`、`REDIS_PASSWORD`。

### 2. 部署

```bash
git push origin feature/stock
# Railway 自動偵測 Dockerfile 或 uvicorn 啟動指令
```

### 3. 驗證推播

- 在 Taipei 時間 08:30 或之後的整點/半點，Telegram 應收到台股訊息
- 在 Taipei 時間 17:00 或之後，應收到美股訊息
- Railway Logs 可查看排程觸發記錄

---

## 執行測試

```bash
# 全部測試
uv run pytest

# 只跑排程相關測試
uv run pytest tests/test_scheduler.py -v

# 覆蓋率報告
uv run pytest --cov=src --cov-report=term-missing
```

### 關鍵測試案例

**Endpoint 測試**：

| 測試 | 說明 |
|------|------|
| `test_us_telegram_success` | 正常美股 ticker 推播成功 |
| `test_us_telegram_lowercase` | `aapl` 自動轉大寫 `AAPL` |
| `test_us_telegram_invalid_ticker` | 非字母 ticker 被過濾，回傳 error |
| `test_us_telegram_empty` | 空 stock 參數回傳 error |
| `test_tw_telegram_rich_format` | 台股 endpoint 現在送出富格式訊息 |

**時間窗口測試**：

| 測試 | 說明 |
|------|------|
| `test_tw_window_start` | 08:30 應在台股窗口內 |
| `test_tw_window_end` | 14:00 應在台股窗口內 |
| `test_tw_window_before` | 08:29 不在台股窗口 |
| `test_tw_window_after` | 14:01 不在台股窗口 |
| `test_tw_window_weekend` | 周六 09:00 不在台股窗口 |
| `test_us_window_evening` | 周三 17:00 在美股窗口 |
| `test_us_window_midnight` | 周四 00:00 在美股窗口 |
| `test_us_window_end` | 周四 04:00 在美股窗口 |
| `test_us_window_after_end` | 周四 04:01 不在美股窗口 |
| `test_us_window_sunday` | 周日 20:00 不在美股窗口 |
| `test_us_window_sat_early` | 周六 03:00 在美股窗口（周五夜延伸） |
| `test_us_window_sat_late` | 周六 05:00 不在美股窗口 |

---

## 程式碼品質檢查

```bash
# Linting + Formatting
uv run ruff check . --fix && uv run ruff format .

# 型別檢查
uv run mypy src/

# Pre-commit（含 secrets scan）
uv run pre-commit run --all-files
```
