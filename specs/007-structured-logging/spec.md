# Spec 007 — 結構化日誌整合（Better Stack）

## 背景與目標

目前專案使用 Python 標準 `logging`，輸出純文字格式，無法被外部服務結構化索引與分析。
本 spec 目標是將 log 改為 JSON 格式，並透過 `logtail-python` 送到 Better Stack，
讓 Better Stack Dashboard 可以針對 Performance Log 與 Error Log 做視覺化分析與告警。

**部署架構決策**：採用「logtail-python 直送 Better Stack」方案。

```
FastAPI
    ↓  LogtailHandler（非同步，background thread）
Better Stack API
    ↓
Better Stack Dashboard（查詢、圖表、Alert）
```

理由：
- Railway Hobby plan 無 Log Drain 功能
- `logtail-python` 官方 handler 非同步送出，不阻塞 API 回應
- Better Stack 免費版（1GB/月）對此規模足夠
- 本地開發不需模擬，`LOG_FORMAT=text` 看終端機，`LOGTAIL_SOURCE_TOKEN` 留空不啟用

---

## User Story

- **US-001**：身為維運人員，我想在 Kibana 看到每支 API 的 P95 回應時間，以便找出效能瓶頸。
- **US-002**：身為維運人員，我想在 Kibana 看到 Error/Warning log，並依 route 與 message 篩選，以便快速定位問題。
- **US-003**：身為開發者，我想在本地用 `LOG_FORMAT=json` 看到 JSON 格式的 stdout，確認欄位正確後再部署到 Railway，不需要在本地起 ELK。

---

## 功能需求

### FR-001：JSON Formatter 改造

- 加入 `python-json-logger` 依賴
- 將 `main.py` 的 `_LOGGING_CONFIG` formatter 改為 `pythonjsonlogger.jsonlogger.JsonFormatter`
- 透過環境變數 `LOG_FORMAT` 控制格式：
  - `json`（預設）：輸出 JSON Lines，適合 ELK
  - `text`：輸出純文字，適合本地開發不啟動 ELK 時閱讀
- 不得修改現有 logger 的 level 設定與 `disable_existing_loggers: False`

### FR-002：Performance Log 欄位規格

每個 API 請求結束後輸出一條 PERF log，JSON 欄位如下：

```json
{
  "timestamp": "2026-05-09T10:23:45.123Z",
  "level": "INFO",
  "log_type": "PERF",
  "service": "fastapistock",
  "environment": "production",
  "route": "get_stocks",
  "method": "GET",
  "status_code": 200,
  "duration_ms": 333,
  "client_ip": "1.2.3.4",
  "pid": 12345
}
```

**必要欄位**：`timestamp`, `level`, `log_type`, `route`, `method`, `status_code`, `duration_ms`
**選用欄位**：`client_ip`, `pid`, `service`, `environment`

改造重點：`LoggingMiddleware` 的 PERF log 目前將所有欄位塞入 `msg` 字串，
需改為透過 `extra={}` 傳遞各欄位，讓 JsonFormatter 序列化為獨立的 JSON key。

### FR-003：Error Log 欄位規格

WARNING 及 ERROR level 的 log，JSON 欄位如下：

```json
{
  "timestamp": "2026-05-09T10:23:45.123Z",
  "level": "ERROR",
  "log_type": "ERROR",
  "service": "fastapistock",
  "environment": "production",
  "route": "get_stocks",
  "method": "GET",
  "message": "Portfolio fetch failed: HTTP 500",
  "exc_info": "Traceback ...",
  "pid": 12345
}
```

**必要欄位**：`timestamp`, `level`, `message`
**選用欄位**：`route`, `method`, `exc_info`, `pid`

改造重點：目前 `report_service.py`、`report_history_repo.py`、`sheet_writer.py` 使用
`extra={'duration_ms': ..., 'error_type': ..., 'job_id': ...}` 呼叫，
JSON formatter 需確保 extra 欄位被序列化，不得丟棄。

### FR-004：LogtailHandler 整合

- 加入 `logtail-python` 依賴
- 在 FastAPI lifespan `startup` 時，若 `LOGTAIL_SOURCE_TOKEN` 非空，將 `LogtailHandler` 加入 root logger
- `LogtailHandler` 使用 background thread 非同步送出，不阻塞 API
- Better Stack 側設定（infra 操作）：
  1. 至 [Better Stack](https://betterstack.com) 建立免費帳號
  2. Logs → Sources → Connect source → 選 HTTP source
  3. 複製 Source Token → 填入 Railway 環境變數 `LOGTAIL_SOURCE_TOKEN`

### FR-005：本地開發驗證方式

本地**不需要啟動任何外部服務**：

- `LOGTAIL_SOURCE_TOKEN` 留空 → LogtailHandler 不啟用，只看終端機
- 設 `LOG_FORMAT=json`，確認 JSON 格式正確：
  ```bash
  uv run uvicorn src.fastapistock.main:app --reload 2>&1 | jq '.'
  ```
- 確認 `log_type`、`route`、`method`、`duration_ms`、`status_code` 欄位存在且型別正確
- 若要測試實際送到 Better Stack，填入真實 Token 後呼叫一次 API，去 Better Stack Live Tail 確認

---

## 非功能需求

- **NFR-001**：改造後現有 log 覆蓋範圍不得縮減（Middleware、Service、Repository 均需保留）
- **NFR-002**：stdout JSON 寫入不得造成 API 回應延遲，stdout 為 kernel buffer 寫入，預期影響 < 1ms
- **NFR-003**：`LOG_FORMAT=text` 時，純文字輸出的可讀性不得低於改造前
- **NFR-004**：新增依賴（`python-json-logger`, `logtail-python`）須加入 `pyproject.toml`，不得直接編輯 `requirements.txt`

---

## 排除範圍

- 不實作 AsyncElasticsearchHandler（本 spec 選擇 Better Stack 方案）
- 不在 `docker-compose.dev.yml` 加入任何 ELK/logging 相關 service
- 不設定 Railway Log Drain（Hobby plan 不支援）
- 不實作 Index Lifecycle Management（ILM）/ Index Template（留待後續 spec）
- 不加入 Kibana Dashboard 設定（留待後續 spec）
- 不改動 `tests/` 下的測試 log 輸出行為

---

## 資料模型

### Performance Log Index Mapping（`fastapistock-perf-*`）

| 欄位 | 型別 | 必要 | 說明 |
|------|------|------|------|
| `@timestamp` | date | Y | ISO8601 UTC |
| `level` | keyword | Y | INFO |
| `log_type` | keyword | Y | 固定值 PERF |
| `service` | keyword | Y | 固定值 fastapistock |
| `environment` | keyword | Y | production / development |
| `route` | keyword | Y | FastAPI route name |
| `method` | keyword | Y | HTTP method |
| `status_code` | integer | Y | HTTP status code |
| `duration_ms` | integer | Y | 毫秒 |
| `client_ip` | ip | N | 用戶端 IP |
| `pid` | integer | N | Process ID |

### Error Log Index Mapping（`fastapistock-error-*`）

| 欄位 | 型別 | 必要 | 說明 |
|------|------|------|------|
| `@timestamp` | date | Y | ISO8601 UTC |
| `level` | keyword | Y | WARNING / ERROR |
| `log_type` | keyword | Y | ERROR |
| `service` | keyword | Y | 固定值 fastapistock |
| `environment` | keyword | Y | production / development |
| `message` | text | Y | log 訊息 |
| `route` | keyword | N | 來自 RequestContext |
| `method` | keyword | N | HTTP method |
| `exc_info` | text | N | Exception traceback |
| `error_type` | keyword | N | 來自 extra |
| `job_id` | keyword | N | 來自 report pipeline extra |
| `duration_ms` | integer | N | 來自 extra |

---

## 環境變數清單

| 變數名稱 | 必要 | 預設值 | 說明 |
|---------|------|--------|------|
| `LOG_FORMAT` | N | `json` | `json`（Railway 生產）或 `text`（本地開發） |
| `LOG_LEVEL` | N | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOGTAIL_SOURCE_TOKEN` | N | `""` | Better Stack Source Token，空值時不啟用 handler |
| `SERVICE_NAME` | N | `fastapistock` | 注入每條 log 的 service 欄位 |
| `ENVIRONMENT` | N | `production` | 注入每條 log 的 environment 欄位 |

---

## Edge Cases

- `LogRecord.exc_info` 序列化失敗（非 JSON serializable 物件）→ 強制轉 `str()`
- `duration_ms` 欄位型別衝突（float vs int）→ 統一轉 `int(round(...))`
- 在 `text` 模式下，extra 欄位不自動出現在 msg → 維持現狀，不補回
