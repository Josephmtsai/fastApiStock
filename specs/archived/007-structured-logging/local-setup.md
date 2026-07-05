# Local 開發環境說明

## 結論：本地不需要外部服務

本 spec 採用 **logtail-python 直送 Better Stack** 架構，FastAPI 只負責寫 stdout 與呼叫 LogtailHandler。
本地開發**不需要**啟動 Elasticsearch、Kibana 或任何 ELK 服務。

---

## 本地 vs Railway 生產差異

| 項目 | 本地開發 | Railway 生產 |
|------|---------|-------------|
| log 輸出 | stdout（終端機直接看） | stdout + LogtailHandler → Better Stack |
| `LOG_FORMAT` | `text`（預設，方便閱讀） | `json`（必須設定） |
| `LOGTAIL_SOURCE_TOKEN` | **留空**（不啟用 handler） | 填入 Better Stack Source Token |
| 外部服務需求 | **不需要** | Better Stack（免費版 1GB/月） |
| 驗證方式 | 終端機看 / `jq` 驗證 JSON | Better Stack Live Tail / Dashboard |

---

## 本地開發設定

### 一般開發（純文字，最方便）

`.env` 或啟動指令：
```env
LOG_FORMAT=text
LOG_LEVEL=INFO
SERVICE_NAME=fastapistock
ENVIRONMENT=development
LOGTAIL_SOURCE_TOKEN=
```

`LOGTAIL_SOURCE_TOKEN` 留空時 `LogtailHandler` 不啟用，終端機直接看 log，與改造前相同。

### 驗證 JSON 格式正確性（上 PR 前做一次）

```env
LOG_FORMAT=json
LOGTAIL_SOURCE_TOKEN=
```

啟動後呼叫 API，stdout 輸出用 `jq` 驗證：
```bash
uv run uvicorn src.fastapistock.main:app --reload 2>&1 | jq '.'
```

確認以下欄位存在且型別正確即可：
- PERF log：`log_type`, `route`, `method`, `status_code`, `duration_ms`（integer）
- ERROR log：`level`, `message`
- 每條 log：`service`（`fastapistock`）、`environment`（`development`）

### 測試實際送到 Better Stack

僅需填入真實 Token 並呼叫一次 API，即可在 Better Stack Live Tail 確認：
```env
LOG_FORMAT=json
LOGTAIL_SOURCE_TOKEN=<your-source-token>
```

> **注意**：真實 Token 不得 commit 至 `.env`，只填入 `.env.local` 或 Railway Dashboard。

---

## Railway 生產設定

在 Railway Dashboard → Variables 加入：

```
LOG_FORMAT=json
SERVICE_NAME=fastapistock
ENVIRONMENT=production
LOGTAIL_SOURCE_TOKEN=<token-from-better-stack>
```

Better Stack Source Token 取得方式：
1. 至 [Better Stack](https://betterstack.com) 建立免費帳號
2. Logs → Sources → Connect source → 選 HTTP source
3. 複製 Source Token → 填入 Railway 環境變數 `LOGTAIL_SOURCE_TOKEN`

---

## 常見問題

### 本地要怎麼確認 extra 欄位（job_id、duration_ms）有沒有出現？

手動觸發 report pipeline，用 `LOG_FORMAT=json` 啟動，過濾 log：
```bash
uv run uvicorn src.fastapistock.main:app --reload 2>&1 | jq 'select(.job_id != null)'
```

### `LOG_FORMAT=text` 時 extra 欄位不見了

預期行為。`text` 模式下 extra 欄位不自動出現在 msg，這是設計決策。
需要看 extra 欄位請切換 `LOG_FORMAT=json`。

### `LOGTAIL_SOURCE_TOKEN` 留空時會報錯嗎？

不會。startup 邏輯判斷 token 為空時直接跳過 `LogtailHandler` 初始化，
現有 stdout log 行為完全不受影響。
