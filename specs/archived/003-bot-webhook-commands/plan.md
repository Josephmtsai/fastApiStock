# Implementation Plan: Telegram Bot Webhook with Command Menu & Quarterly Investment Achievement Rate

**Branch**: `003-bot-webhook-commands` | **Date**: 2026-04-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-bot-webhook-commands/spec.md`

## Summary

新增 Telegram Bot Webhook 接收入口，讓用戶可主動發送指令（`/q`, `/us`, `/tw`, `/help`）查詢資料；
同時新增季度投資達成率計算功能（讀取 Google Sheets 特定 GID），並保留現有排程主動推送行為不受影響。

## Technical Context

**Language/Version**: Python 3.11+（`.python-version` 管理）
**Primary Dependencies**: FastAPI、httpx、redis-py、python-dotenv（均已在 pyproject.toml）
**Storage**: Redis（快取）、Google Sheets CSV 匯出（投資計畫資料來源）
**Testing**: pytest（`tests/unit/`, `tests/integration/`）
**Target Platform**: Linux server（與現有部署一致）
**Project Type**: Web Service（FastAPI）
**Performance Goals**: Cached 端點 ≤ 200ms；live-fetch 端點 ≤ 2s（遵循 Constitution IV）
**Constraints**: 所有對外 HTTP 請求須設定 timeout；Redis 不可用時需 graceful fallback
**Scale/Scope**: 單一授權用戶；無多租戶需求

## Constitution Check

*GATE: 進入 Phase 0 前驗證，Phase 1 設計後再驗證*

| 原則 | 狀態 | 說明 |
|------|------|------|
| I. Code Quality | ✅ PASS | 所有新增函式須有 type hints + Google-style docstrings；無 `print()`、`Any`；設定值（GID、secret）從 env 讀取 |
| II. Testing Standards | ✅ PASS | 新增 unit tests（`investment_plan_repo`, `investment_plan_service`）與 integration test（`test_webhook.py`）；目標 80%+ 覆蓋率 |
| III. API Consistency | ✅ PASS | Webhook POST endpoint 回應 `ResponseEnvelope`；路由透過 `APIRouter` 定義；業務邏輯在 service 層 |
| IV. Performance & Resilience | ✅ PASS | Sheets CSV 快取使用現有 `redis_cache`；Telegram API 呼叫保留 `_REQUEST_TIMEOUT=10`；Redis 失敗時 fallback 至 live fetch |
| V. Observability | ✅ PASS | 所有端點已受 `LoggingMiddleware` 覆蓋；新增的 service 層使用 `logging.getLogger(__name__)` |

**Phase 1 後再次確認**：data-model 與 contracts 設計完成後需複查 Constitution I、III 合規性。

## Project Structure

### Documentation (this feature)

```text
specs/003-bot-webhook-commands/
├── plan.md              # 本文件（/speckit.plan 輸出）
├── research.md          # Phase 0 研究結論
├── data-model.md        # Phase 1 資料模型
├── quickstart.md        # Phase 1 快速啟動指南
├── contracts/           # Phase 1 介面合約
│   └── webhook.md
└── tasks.md             # Phase 2 輸出（/speckit.tasks）
```

### Source Code (repository root)

```text
src/fastapistock/
├── config.py                              # 新增 2 個 env var
├── main.py                                # 新增 webhook router + lifespan setMyCommands
├── repositories/
│   ├── portfolio_repo.py                  # 不變
│   └── investment_plan_repo.py            # 新增：讀取季度計畫 Sheet
├── services/
│   ├── telegram_service.py                # 新增 reply_to_chat() helper
│   └── investment_plan_service.py         # 新增：達成率計算邏輯
└── routers/
    ├── telegram.py                        # 不變（排程用）
    ├── us_telegram.py                     # 不變（排程用）
    └── webhook.py                         # 新增：POST /api/v1/webhook/telegram

tests/
├── unit/
│   ├── test_investment_plan_repo.py       # 新增
│   └── test_investment_plan_service.py    # 新增
└── integration/
    └── test_webhook.py                    # 新增
```

**Structure Decision**: 沿用現有 Single Project 結構，依責任分層（routers / services / repositories）；
不新增 package，僅在各層新增對應模組。

## Phases

### Phase 0：研究 → `research.md`

- Telegram webhook 設定方式（setWebhook API call）
- Telegram setMyCommands 啟動時機與呼叫方式
- `X-Telegram-Bot-Api-Secret-Token` 驗證機制
- Google Sheets CSV 匯出 GID 欄位對應（B=index 1, C=index 2, F=index 5, G=index 6）
- Redis cache key 命名規範（沿用現有 `stock:` 前綴模式）

### Phase 1：設計 → `data-model.md`, `contracts/`, `quickstart.md`

**資料模型**：
- `InvestmentPlanEntry`：季度計畫單筆資料
- `TelegramMessage`：Telegram Update 的 message 子物件（Pydantic）
- `TelegramFrom`：訊息發送者（Pydantic）
- `TelegramChat`：聊天對象（Pydantic）
- `TelegramUpdate`：Telegram webhook payload（Pydantic）
- `QuarterlyAchievementReport`：達成率計算結果

**介面合約**：
- `POST /api/v1/webhook/telegram`：Telegram 回呼端點

**設計限制**：
- `reply_to_chat()` 新增在 `telegram_service.py`，共用 `_TELEGRAM_API_BASE` 與 `_REQUEST_TIMEOUT`
- 不引入 python-telegram-bot 套件（直接使用 httpx，與現有模式一致）
- Cache key：`investment_plan:{date}` 格式，TTL 使用 `PORTFOLIO_CACHE_TTL`

## Complexity Tracking

> 無 Constitution 違規，本節為空。
