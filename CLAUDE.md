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

## 3. 安全與防禦性設計 (Security & Resilience)
- **安全性**:
  - 嚴禁 Hardcode Secret，統一由 `python-dotenv` 讀取環境變數。
  - 使用參數化查詢 (Parameterized Queries) 防禦 SQL 注入。
- **攻擊防護**:
  - 所有 API 路由必須實作 **Rate Limiting** (限流)，防範 DoS/暴力破解。
  - 對外請求 (Outgoing Requests) 必須設定 `timeout`。
- **台股開發專屬**: 呼叫 API 須實作隨機延遲 (Random Sleep)，並建立 Local Cache 避免重複抓取。

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
