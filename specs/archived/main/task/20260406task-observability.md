## Task: Structured Logging Middleware & API Index Page

**Constitution**: Principle V (Observability) — v1.2.0
**Branch**: `feature/stock`

---

### 1. Request / Response / Performance Logging Middleware

實作一個統一的 logging middleware，套用到所有 API route（含 health），
每次 request 產生三行 log：

**Request Log (進入時)**
```
{DateTime} {ProcessId} {Method} {ClientIP} {HTTP_METHOD} REQ {RequestData}
```

**Response Log (回傳時)**
```
{DateTime} {ProcessId} {Method} {ClientIP} {HTTP_METHOD} RES {StatusCode} {ResponseData}
```

**Performance Log (回傳時)**
```
{DateTime} {ProcessId} {Method} PERF {ResponseTimeMs}ms
```

實作要求：
- 以 Starlette `BaseHTTPMiddleware` 或 pure ASGI middleware 實作
- 放在 `src/fastapistock/middleware/logging.py`
- `DateTime` 為 ISO 8601（含毫秒），`ProcessId` 為 `os.getpid()`
- `Method` 從 route operation name 或 path 取得
- `ClientIP` 優先讀 `X-Forwarded-For`，fallback `request.client.host`
- `RequestData` 包含 path params + query params（body 視情況截斷）
- `ResponseData` 截斷超過 500 字的 body，避免 log 爆量
- 敏感欄位（password, token, secret）須 mask 為 `***`
- Log level: 2xx → `INFO`、4xx → `WARNING`、5xx → `ERROR`；PERF 一律 `INFO`
- log format 統一在 `main.py` 的 `_LOGGING_CONFIG` 設定，middleware 只負責產出 message

### 2. API Index Page（首頁）

在根路由 `GET /` 新增一個頁面，列出目前所有可用的 API endpoints：

| Method | Path | Summary |
|--------|------|---------|
| GET | `/health` | Health check |
| GET | `/api/v1/stock/{id}` | Get quotes for one or more Taiwan stocks |
| GET | `/api/v1/tgMessage/{id}?stock=` | Push stock info to a Telegram user |

實作要求：
- 新增 router 或直接在 `main.py` 用 `app.routes` 動態產生清單
- 回傳格式採用 `ResponseEnvelope[list[dict]]`，data 為每個 route 的 method / path / summary
- 若偏好 HTML 首頁，可回傳簡易 HTML table（二擇一皆可）

### 3. 測試

- 寫 middleware 的 unit test：驗證 log 輸出包含 REQ / RES / PERF 三行
- 寫 `GET /` index page 的 integration test：驗證回傳包含所有已知路由
- 確保既有 test_health / test_stocks 不受影響

### 4. Acceptance Criteria

- [ ] 每支 API call 皆產出 REQ、RES、PERF 三行 structured log
- [ ] Log format 符合 constitution Principle V 定義
- [ ] `GET /` 回傳完整的 API 清單
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src/` 全部通過
- [ ] `uv run pytest` 全部通過
