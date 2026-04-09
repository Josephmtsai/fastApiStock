# Quickstart: Google Sheets 持倉整合

## 1. 設定 Google Sheets

### 確認試算表公開分享

1. 開啟你的 Google Sheets
2. 右上角「分享」→「知道連結的人」→「檢視者」
3. 確認可以在無登入的瀏覽器中直接開啟連結

### 取得必要的 ID

從試算表 URL 取得兩個值：
```
https://docs.google.com/spreadsheets/d/1RDRpwuXjHH.../edit?gid=1004709448
                                        ^^^^^^^^^^^^                 ^^^^^^^^^^
                                        GOOGLE_SHEETS_ID             GOOGLE_SHEETS_PORTFOLIO_GID
```

### 確認欄位結構

持倉分頁（gid=1004709448）必須符合以下結構：

| A | B | C | D | E | F | G | H | I |
|---|---|---|---|---|---|---|---|---|
| 代號 | 股票名稱 | 持股數 | ... | ... | 平均成本 | ... | ... | 未實現損益 |
| 2330 | 台積電 | 1000 | ... | ... | 820.00 | ... | ... | 75000 |

> 第一列為標題列，系統自動略過

## 2. 設定環境變數

```env
GOOGLE_SHEETS_ID=1RDRpwuXjHHU9nr1BYPk_k6fzRO_lnhnmwrBLws3oHjg
GOOGLE_SHEETS_PORTFOLIO_GID=1004709448
PORTFOLIO_CACHE_TTL=3600
```

## 3. 驗證設定

**本地測試**：
```bash
# 直接測試 CSV 匯出是否可存取
curl "https://docs.google.com/spreadsheets/d/${GOOGLE_SHEETS_ID}/export?format=csv&gid=${GOOGLE_SHEETS_PORTFOLIO_GID}"
```

應看到 CSV 格式輸出（第一行為標題）。若看到 HTML 登入頁，表示試算表未公開。

**手動觸發推播**：
```bash
curl "http://localhost:8000/api/v1/tgMessage/YOUR_CHAT_ID?stock=2330"
```

Telegram 收到的訊息應包含「持倉」區塊（若 2330 在試算表中）：
```
🔺 *2330* 台積電
   現價: `895.00 TWD`   昨收: `885.00`
   漲跌: `+10.00` (+1.13%)
   ─── 持倉 ───
   持股: `1,000`   成本: `820.00` (+9.15%)
   損益: `+75,000 TWD`
   RSI(14): `62.3`
   ...
```

## 4. 快取行為

- 首次推播：抓取試算表 → 存入 Redis → 顯示持倉
- 後續推播（TTL 內）：直接讀 Redis，不重新抓取
- 清除快取（手動）：
  ```bash
  redis-cli DEL portfolio:tw
  ```

## 5. 疑難排解

| 症狀 | 原因 | 解法 |
|------|------|------|
| 持倉區塊不顯示 | 代號不在試算表 A 欄 | 確認代號完全一致（如 `2330` vs `2330 ` 多空格） |
| log 出現 warning `GOOGLE_SHEETS_ID not configured` | env var 未設 | 補上 .env 設定 |
| log 出現 `HTTP error 302` | 試算表未公開 | 重新設定分享權限 |
| 損益顯示錯誤 | I 欄格式問題 | 確認 I 欄為純數字或含千分位逗號的數字字串 |
