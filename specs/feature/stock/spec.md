# Spec：定時股票推播排程 (Scheduled Stock Push)

**Branch**: `feature/stock` | **日期**: 2026-04-09 | **狀態**: Draft

## 概述

在現有 FastAPI 服務中加入 APScheduler，每 30 分鐘自動抓取股票資料，透過
Telegram Bot 推送格式化技術分析訊息給單一指定用戶。依照 Asia/Taipei 時區的
時間窗口，分別推送台股與美股資訊。

## 功能需求

### 1. 排程規則

| 市場 | 推播日 | 時間窗口 (Asia/Taipei) | 頻率 |
|------|--------|------------------------|------|
| 台股 | 周一～五 | 08:30 – 14:00 | 每 30 分鐘 |
| 美股 | 周一～五 17:00 起 + 周二～六 00:00 – 04:00 | 17:00 – 隔日 04:00 | 每 30 分鐘 |

> 美股推播橫跨午夜：以台灣時間為準，周五 17:00 開始，到周六 04:00 結束。
> 周日不推任何市場。

排程器在 FastAPI `lifespan` 啟動/停止，使用 APScheduler `AsyncIOScheduler`，
timezone 固定設為 `Asia/Taipei`。

### 2. 技術指標（推播訊息內容）

每支股票推播以下資訊：

**推播顯示欄位**（傳送給用戶的訊息內容）：

| 欄位 | 說明 |
|------|------|
| 現價 / 前收 | 最新收盤價與前一交易日收盤價 |
| 漲跌金額 / 漲跌幅 | 相對前收計算 |
| 盤前價格（僅美股） | 盤前交易價格及相對前收漲跌幅；非盤前時段不顯示 |
| RSI(14) | 相對強弱指數；> 70 標註超買，< 30 標註超賣 |
| MA20 / MA50 | 短中期均線，標示現價在均線上方↑或下方↓ |
| 52 週區間位置 | 歷史高低點與現價百分位 |
| 綜合評分與判斷 | -8 ~ +8，>= +3 看漲，<= -3 看跌，其餘中性 |

**內部計算欄位**（用於評分，不顯示於訊息）：MACD(12,26,9)、Bollinger Bands(20,2)、成交量比

### 3. 新增 US Stock Repository

現有 `twstock_repo.py` 硬寫 `.TW` suffix，美股需要新的 repository：

- `src/fastapistock/repositories/us_stock_repo.py`
- ticker 直接使用 yfinance 原生 symbol（如 `AAPL`、`TSLA`）
- 取 6 個月歷史資料（足夠計算 MA50 和 Bollinger Bands）
- 同樣實作 random delay (0.5–2 s)、timeout、Redis cache

### 4. RichStockData Schema

新增 `RichStockData` Pydantic model（位於 `schemas/stock.py`），包含所有
技術指標欄位，供排程訊息格式化使用。現有 `StockData` 保持不動（API 相容性）。

### 5. Telegram 訊息格式

使用 Telegram `parse_mode=MarkdownV2` 格式，包含 emoji 與技術分析。
參考 `/sample/stock_check.py` 的排版風格，重新實作，不直接使用 sample 程式碼。

**台股訊息範例：**

**台股範例：**

```
📈 *台股定時推播*
🕐 2026\-04\-09 09:00 \| Asia/Taipei
\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-

🔺 *0050* 元大台灣50
   現價: `195\.50 TWD`   昨收: `193\.20`
   漲跌: `\+2\.30` \(\+1\.19%\)
   RSI\(14\): `58\.3`
   均線: `MA20:192↑  MA50:188↑`
   近期區間: `150\.00 ─── 195\.50 ─── 220\.00` \(70%位置\)
   ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
   ⚖️ *中性觀望* \(評分 1/8\)
   ✅ 站上 MA20 短期均線
   ❌ RSI=58 偏超買區

\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-
_由 FastAPI Stock Bot 自動產生_
```

**美股範例**（header 改為「美股定時推播」，幣別 USD，盤前時段額外顯示盤前行）：

```
🔺 *AAPL* Apple Inc\.
   現價: `195\.50 USD`   前收: `193\.20`
   漲跌: `\+2\.30` \(\+1\.19%\)
   盤前: `196\.00 USD`  \(\+1\.45%\)
   RSI\(14\): `62\.1`
   均線: `MA20:190↑  MA50:185↑`
   近期區間: `150\.00 ─── 195\.50 ─── 230\.00` \(65%位置\)
   ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
   📈 *看漲* \(評分 4/8\)
```

### 6. 環境變數設定

```env
# 已存在
TELEGRAM_TOKEN=your_bot_token

# 新增
TELEGRAM_USER_ID=123456789        # Telegram chat/user ID（自己）
TW_STOCKS=0050,2330,2454          # 台股代碼，逗號分隔
US_STOCKS=AAPL,TSLA,NVDA          # 美股代碼，逗號分隔
```

## 非功能需求

| 項目 | 要求 |
|------|------|
| 錯誤隔離 | 排程 job 失敗不影響 HTTP API 正常運作 |
| 快取 | 美股資料同樣走 Redis cache（TTL=5 min） |
| Timeout | 所有外部請求設定 timeout（yfinance 10 s，Telegram 10 s） |
| 部署環境 | Railway 單一 instance，APScheduler 跑在同一 process |
| 日誌 | 每次推播成功/失敗均記錄 logging（不用 print()） |
| 型別 | 所有 public function 完整型別標記，mypy strict 通過 |

## 手動觸發 API（新增）

除了定時排程，同時提供手動觸發 endpoint 供測試與臨時查詢使用。
兩個 endpoint 與排程器共用同一套 service 層，不重複實作邏輯。

### 升級：台股手動推播

```
GET /api/v1/tgMessage/{id}?stock=0050,2330
```

- **現有 endpoint，改用富格式訊息**（RichStockData + MarkdownV2）
- `{id}`：Telegram chat/user ID
- `stock`：逗號分隔台股代碼（數字）
- 回應格式不變：`{ "status": "success"|"error", "data": null, "message": "..." }`

### 新增：美股手動推播

```
GET /api/v1/usMessage/{id}?stock=AAPL,TSLA,NVDA
```

- `{id}`：Telegram chat/user ID
- `stock`：逗號分隔美股 ticker（英文，大小寫不敏感，自動轉大寫）
- 回應格式相同 envelope
- Rate limiting 與現有 `/api/v1/tgMessage` 共用同一套 middleware 設定

## 不在本次範圍

- 多用戶訂閱管理
- 動態新增/移除訂閱股票的 API endpoint
- 條件觸發式推播（如突破均線才發）
- 持倉監控（ft_monitor 功能）
- 美股盤後即時報價
- 台股盤前價格（yfinance 台股不提供可靠盤前資料）

## 驗收條件

1. 在 Asia/Taipei 08:30 啟動排程，每 30 分鐘觸發一次台股推播（周一~五）
2. 在 Asia/Taipei 17:00 啟動美股推播，跨夜持續到 04:00（含周六凌晨）
3. 時間窗口外不觸發任何推播
4. Telegram 收到格式正確的 MarkdownV2 訊息，含所有技術指標
5. Redis cache 命中時不重複呼叫 yfinance
6. `GET /api/v1/tgMessage/{id}?stock=0050` 回傳富格式 Telegram 訊息
7. `GET /api/v1/usMessage/{id}?stock=AAPL` 回傳美股富格式 Telegram 訊息
8. 非數字台股代碼與非英文美股 ticker 被靜默過濾
9. 測試覆蓋率 ≥ 80%（時間窗口邏輯、指標計算必測）
