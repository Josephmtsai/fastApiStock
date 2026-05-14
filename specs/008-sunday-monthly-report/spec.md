# 008 — 月報改為每月第一個周日觸發

## 背景

目前月報排程設定為「每月 1 日 21:00」，與週報（每周日 21:00）分開執行。
使用者希望月報改為在**每月第一個周日 21:00**，與當週週報同一時段發出，
讓月報與周報在同一個習慣性時間點集中接收。

## 需求

### User Story

> 作為投資組合追蹤使用者，
> 我希望在每月第一個周日晚上 21:00，
> 先收到當週週報，再收到上個月的月報，
> 讓我能在同一個時段回顧本週與上月表現。

### 驗收條件 (Acceptance Criteria)

| # | 條件 |
|---|------|
| AC-1 | 每月第一個周日 21:00，週報和月報均發送至 Telegram（兩則獨立訊息） |
| AC-2 | 每月 1 日 21:00 不再觸發月報 |
| AC-3 | 非第一個周日的其他周日，只發週報，不發月報 |
| AC-4 | 月報內容為「上個月」的資料（`_monthly_window()` 邏輯不變） |
| AC-5 | Postgres UPSERT、Google Sheets 歸檔行為與現有月報完全一致 |

## 範疇

### 修改

- `src/fastapistock/scheduler.py`：將 `monthly_report` job 的 trigger 由
  `CronTrigger(day=1, hour=21, minute=0)` 改為
  `CronTrigger(day_of_week='sun', day='1-7', hour=21, minute=0)`

### 不修改

- `report_service.py`（`_monthly_window()` 已以 `now` 計算上個月，邏輯正確）
- `telegram_service.py`（發送機制不變，仍為兩則獨立訊息）
- Postgres / Redis / Google Sheets 相關 repo（行為不變）
- 任何 API 路由

## 邊界條件

| 情境 | 行為 |
|------|------|
| 每月第一個周日 | 週報 + 月報均發出（月報顯示「上個月」） |
| 每月其他周日 | 只發週報 |
| 每月 1 日（非周日） | 不再觸發月報 |
| 排程延誤（例如應用重啟） | APScheduler misfire 預設行為維持不變 |
| 五月第一個周日（2026-05-03）呼叫 `_monthly_window()` | 回傳 2026-04 |

## 技術細節

APScheduler `CronTrigger` 支援同時指定 `day_of_week` 與 `day` 範圍：

```python
CronTrigger(day_of_week='sun', day='1-7', hour=21, minute=0, timezone=str(_TZ))
```

語意：「當月第 1～7 日且為周日」= 每月第一個周日。

## 風險

| 風險 | 說明 | 緩解 |
|------|------|------|
| 月報延後最多 6 天 | 若 1 日為周一，月報移到 7 日 | 月報性質不需即時，可接受 |
| 首次切換漏發 | 若本月 1 日月報已執行，改排程後本月不再重跑 | 可用 `POST /api/v1/reports/monthly/send` 手動補發 |
