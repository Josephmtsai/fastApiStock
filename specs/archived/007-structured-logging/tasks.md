# Tasks 007 — 結構化日誌整合（Better Stack）

## 架構決策

採用 **logtail-python 直送 Better Stack** 方案：
- FastAPI 透過 `LogtailHandler` 非同步送 log 到 Better Stack
- Railway Hobby plan 不支援 Log Drain，此方案無此限制
- 本地開發 `LOGTAIL_SOURCE_TOKEN` 留空，只看終端機，不需要外部服務

## 依賴關係

```
T001 → T002 → T003
              T004
       T002 → T005 → T006
```

---

## T001 — 加入依賴套件

**描述**：加入 `python-json-logger` 與 `logtail-python` 依賴。

```bash
uv add python-json-logger logtail-python
```

**AC**：
- `uv run python -c "import pythonjsonlogger; from logtail import LogtailHandler"` 不報錯
- `pyproject.toml` 與 `uv.lock` 已更新

**依賴**：無

---

## T002 — 改造 `_LOGGING_CONFIG` JSON Formatter

**描述**：修改 `src/fastapistock/main.py` 的 `_LOGGING_CONFIG`，根據 `LOG_FORMAT` 環境變數切換 formatter：

- `LOG_FORMAT=json`（預設）→ `pythonjsonlogger.jsonlogger.JsonFormatter`
- `LOG_FORMAT=text` → 維持現有純文字 formatter

同時在每條 log 注入固定欄位：
- `service`（`SERVICE_NAME` env，預設 `fastapistock`）
- `environment`（`ENVIRONMENT` env，預設 `production`）

在 FastAPI lifespan `startup` 加入 LogtailHandler：

```python
from logtail import LogtailHandler

async def lifespan(app: FastAPI):
    # startup
    if settings.LOGTAIL_SOURCE_TOKEN:
        logtail_handler = LogtailHandler(source_token=settings.LOGTAIL_SOURCE_TOKEN)
        logging.getLogger().addHandler(logtail_handler)
    yield
    # shutdown（logtail-python 自動 flush）
```

**AC**：
- `LOG_FORMAT=json` 時 stdout 每行為合法 JSON
- `LOG_FORMAT=text` 時輸出與改造前相同
- `LOGTAIL_SOURCE_TOKEN` 空值時不加入 handler，不影響現有行為
- `service`、`environment` 欄位出現在每條 JSON log 中
- `disable_existing_loggers: False` 保持不變

**依賴**：T001

---

## T003 — 改造 `LoggingMiddleware` 輸出結構化欄位

**描述**：修改 `src/fastapistock/middleware/logging.py`，將目前 `%` 字串格式化塞入 msg 的做法，
改為透過 `extra={}` 傳遞各欄位，讓 JsonFormatter 序列化為獨立 JSON key。

**PERF log**（Performance Log 主要來源）：
```python
logger.info(
    'PERF',
    extra={
        'log_type': 'PERF',
        'pid': pid,
        'route': route_name,
        'method': method,
        'status_code': status_code,
        'duration_ms': int(round(elapsed_ms)),
        'client_ip': client_ip,
    }
)
```

**REQ log**：
```python
logger.info(
    'REQ',
    extra={
        'log_type': 'REQ',
        'pid': pid,
        'route': route_name,
        'method': method,
        'client_ip': client_ip,
        'path_params': str(path_params),
        'query_params': str(query_params),
    }
)
```

**RES log**：
```python
logger.info(
    'RES',
    extra={
        'log_type': 'RES',
        'pid': pid,
        'route': route_name,
        'method': method,
        'client_ip': client_ip,
        'status_code': status_code,
    }
)
```

`LOG_FORMAT=text` 時 msg 字串保留簡短描述維持可讀性。

**AC**：
- JSON 模式：`log_type`、`route`、`method`、`status_code`、`duration_ms` 均為獨立 JSON key
- `duration_ms` 型別為 integer
- `LOG_FORMAT=text` 時 log 可讀性合理
- `tests/test_logging_middleware.py` 全數通過

**依賴**：T002

---

## T004 — 確保 `extra` 欄位被 JsonFormatter 序列化

**描述**：確認 `report_service.py`、`report_history_repo.py`、`sheet_writer.py` 的
`extra={'job_id': ..., 'duration_ms': ..., 'error_type': ...}` 呼叫在 JSON 模式下
能正確出現在輸出 JSON 與 Better Stack 中。

若 `python-json-logger` 預設不展開 extra，繼承 `JsonFormatter` 自訂序列化。
處理非 JSON serializable 型別（`Decimal`、`datetime`）→ fallback `str()`。

**AC**：
- `job_id`、`trigger`、`report_type`、`duration_ms`、`error_type` 出現在 JSON log 中
- `Decimal`、`datetime` 不造成 serialize 錯誤
- 新增單元測試驗證 extra 欄位序列化

**依賴**：T002

---

## T005 — 加入 `LOGTAIL_SOURCE_TOKEN` 至環境變數設定

**描述**：
- `src/fastapistock/config.py` 加入 `LOGTAIL_SOURCE_TOKEN: str = ''` 欄位
- `.env.example` 加入說明：
  ```
  # Better Stack（留空則不啟用）
  LOGTAIL_SOURCE_TOKEN=
  LOG_FORMAT=json
  SERVICE_NAME=fastapistock
  ENVIRONMENT=production
  ```
- Railway Dashboard 加入 `LOGTAIL_SOURCE_TOKEN`（值從 Better Stack 取得）

**AC**：
- `config.py` 有 `LOGTAIL_SOURCE_TOKEN` 欄位，預設空字串
- `.env.example` 已更新
- `LOGTAIL_SOURCE_TOKEN` 未加入 `.env`（不能 commit 真實 token）

**依賴**：T002

---

## T006 — 端對端驗證（Better Stack）

**描述**：部署到 Railway 後，驗證 log 正確出現在 Better Stack Dashboard。

驗證步驟：
1. Railway 設定 `LOGTAIL_SOURCE_TOKEN`、`LOG_FORMAT=json`、`ENVIRONMENT=production`
2. 部署後呼叫 `GET /api/v1/health`
3. Better Stack → Live Tail 確認出現 PERF log，含 `duration_ms`、`route`、`status_code`
4. 觸發一個錯誤，確認 ERROR log 出現，含 `level`、`message`
5. Better Stack → Dashboards 建立圖表：
   - API 回應時間（`duration_ms` by `route`）
   - Error rate（`level = ERROR` count by time）

**AC**：
- Better Stack Live Tail 能即時看到 PERF log 與 ERROR log
- `duration_ms` 為 integer 型別（Better Stack 可做數值聚合）
- 至少建立一個 Dashboard 圖表

**依賴**：T005
