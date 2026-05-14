# Python 專案規範與工程準則 (Optimized for UV & Ruff)

## 1. 環境與依賴管理 (Environment)
- **Runtime**: Python 3.11+ (透過 `.python-version` 管理)。
- **Tooling**: 統一使用 **UV** 管理虛擬環境與套件。
- **Dependencies**:
  - 核心依賴記錄於 `pyproject.toml`，鎖定版本使用 `uv.lock`。
  - 禁止直接編輯 `requirements.txt`，若需匯出請用 `uv export`。
  - 嚴禁使用 `conda install` 安裝專案內部的生產依賴。

## 2. 程式碼品質與自動化 (Quality & Automation)
- **Linting & Formatting**: 統一使用 **Ruff**。
  - 遵循 PEP 8，單行長度上限 88 字元。
  - 字串優先使用單引號 `'` (f-strings 亦同)。
  - 指令: `uv run ruff check . --fix && uv run ruff format .`
- **強制型別標記 (Strict Typing)**:
  - 所有 Public Functions 必須包含完整的型別標記 (Type Hints)。
  - **Any 禁令**: 嚴禁使用 `Any`。若第三方庫限制，須加註釋說明。
  - 驗證: `uv run mypy src/`。
- **禁令**: 嚴禁 `eval()`、`exec()`、`print()` (請用 logging) 與模糊的 `except:`。不得使用 `# noqa` 除非有極充分理由。
  - 禁止直接修改bug 需要新開feature branch 修正後commit 在merge到main
- **功能修改**
  - 確保修改造成的舊有功能不被影響到 如果被影響到應由SA提出分析
## 3. 安全與防禦性設計 (Security & Resilience)
- **安全性**:
  - 嚴禁 Hardcode Secret，統一由 `python-dotenv` 讀取環境變數。
  - 使用參數化查詢 (Parameterized Queries) 防禦 SQL 注入。
- **攻擊防護**:
  - 所有 API 路由必須實作 **Rate Limiting** (限流)，防範 DoS/暴力破解。
  - 對外請求 (Outgoing Requests) 必須設定 `timeout`。
- **台股開發專屬**: 呼叫 API 須實作隨機延遲 (Random Sleep)，並建立 Local Cache 避免重複抓取。
- **美股盤前專屬**: `ticker.info['preMarketPrice']` 因 Yahoo Finance upstream 不穩定禁止使用；盤前價格須改用 `ticker.history(prepost=True, interval='1m', period='1d')` 並過濾 Eastern Time 04:00–09:30 時間區間。

## 4. 工程哲學與架構 (Architecture)
- **KISS & YAGNI**: 不重複造輪子，不預先編寫複雜抽象層。
- **API 慣例**:
  - 使用 Blueprints (Flask) 或 APIRouter (FastAPI) 模組化路由。
  - 響應格式: `{ "status": "success"|"error", "data": {}, "message": "" }`。
- **結構**: 函式不超過 50 行，公有成員須撰寫 Google Style Docstrings。

## 5. 測試與提交 (CI/CD & Git)
- **測試**: 使用 `pytest`。新功能必含測試，目標覆蓋率 80%+。
- **Commit**: 遵循 Conventional Commits (feat, fix, docs, test, chore)。
- **Pre-commit**: 本地必須啟用 `pre-commit`。`git commit` 前必須通過所有 Hooks (Ruff, Mypy, Secrets)。
  - 指令: `uv run pre-commit run --all-files`

## 7. Agent Workflow & Handoff Protocol

### 流程

```
SA  ──handoff-sa.json──▶  Developer  ──spawn──▶  codex-reviewer  ──PASS──▶  QA
                                                                  ──FAIL──▶  Developer (修正)
```

### 強制規則（Orchestrator 必須遵守）

1. **Developer 完成後，必須先 spawn codex-reviewer agent，等 review PASS 才能 spawn QA。**
2. **codex-reviewer 回報 FAIL 時，必須回到 Developer 修正，禁止直接 spawn QA。**
3. SA 完成後才能啟動 Developer（`handoff-sa.json` 的 `status` 必須為 `ready`）。
4. QA 完成後回報使用者，不自動 merge 或 deploy。

### Handoff JSON 格式

存放路徑：`specs/<feature>/handoff-<from>.json`

```json
{
  "from": "sa",
  "to": "developer",
  "feature": "007-structured-logging",
  "status": "ready",
  "summary": "一句話說明做了什麼",
  "artifacts": ["specs/.../spec.md", "specs/.../tasks.md"],
  "assumptions": ["假設一", "假設二"]
}
```

Developer 完成時額外加入：

```json
{
  "from": "developer",
  "to": "qa",
  "feature": "007-structured-logging",
  "status": "ready",
  "summary": "實作了 StructuredJsonFormatter、改造 LoggingMiddleware",
  "changed_files": ["src/fastapistock/core/json_formatter.py", "src/fastapistock/main.py"],
  "ac_ref": "specs/007-structured-logging/tasks.md"
}
```

### Context Package（各 agent 只讀需要的）

| 接收方 | 必讀 | 不需要 |
|--------|------|--------|
| Developer | handoff-sa.json + artifacts 列出的所有文件 | 無限制 |
| QA | handoff-dev.json（ac_ref + changed_files）+ tasks.md 的 AC 區塊 | 架構決策、ADR、local-setup.md |

### 每個 Agent 的完成義務

- **SA**：產出 `handoff-sa.json`，artifacts 必須列出所有 spec 文件路徑
- **Developer**：產出 `handoff-dev.json`，changed_files 必須完整列出，告知 orchestrator 可以 spawn **codex-reviewer**（不是直接 spawn QA）
- **codex-reviewer**：產出 review report，回報 PASS/FAIL verdict，PASS 才告知 orchestrator 可以 spawn QA
- **QA**：不產出 handoff，直接以測試報告回報 orchestrator

---

## 6. 知識圖譜 (Knowledge Graph)
專案已建立 graphify 知識圖譜，位於 `graphify-out/graph.json`（786 nodes、1552 edges、30 communities）。

**核心節點（異動前請特別留意）**：`get()`、`RichStockData`、`StockNotFoundError`、`ResponseEnvelope`、`PortfolioEntry`。

**遇到下列情境時，執行 `/graphify query "<問題>"` 查詢圖譜，禁止直接將 graph.json 載入 context**：
- 修改跨模組的共用元件（Redis cache、ResponseEnvelope、RichStockData、StockNotFoundError）
- 回答架構問題或追蹤依賴關係
- 新增功能前確認影響範圍
- 重構前了解社群邊界
