# 009 — 新增 /pnl 與 /history 到 Telegram Bot 快速選單

## Overview

將已實作的 `/pnl` 與 `/history` 兩個指令補入 `main.py` 的 `_BOT_COMMANDS` 串列，
使 Telegram 介面的 `/` 快速選單顯示完整的 6 個可用指令。

---

## 背景與問題描述

Telegram Bot 目前在快速選單（輸入 `/` 時出現的自動補全清單）只顯示 4 個指令：
`/q`、`/us`、`/tw`、`/help`。

然而 `/pnl`（投資組合未實現損益）與 `/history`（查詢歷史報告）：
1. 已在 `src/fastapistock/routers/webhook.py` 的 `_dispatch_message()` 中完整實作
2. 已在 `_HELP_TEXT` 中有說明文字
3. 架構文件 `docs/architecture.md` 序列圖明確標記此為已知缺漏

缺漏原因：`src/fastapistock/main.py` 的 `_BOT_COMMANDS` 串列只納入了 4 個指令，
後續新增的 `/pnl` 與 `/history` 未同步更新此清單。

---

## 現況分析

### 已正確設定的部分

| 層面 | 現況 |
|------|------|
| Webhook dispatcher | `/pnl` 與 `/history` 均已在 `webhook.py` dispatch 邏輯中處理 |
| `/help` 文字 | `_HELP_TEXT` 已包含兩個指令的中文說明 |
| 服務層 | `portfolio_service.get_pnl_reply()` 等均已實作 |

### 缺漏的部分

| 層面 | 缺漏 |
|------|------|
| `_BOT_COMMANDS` | `/pnl` 與 `/history` 未列入，Telegram 快速選單不顯示 |
| `docs/architecture.md` 序列圖 | `setMyCommands` 標籤仍標示舊的 4 個指令，Note 標記為已知缺漏 |

---

## 需求

### 功能需求

1. 將 `/pnl` 加入 `_BOT_COMMANDS`，說明文字：`投資組合未實現損益（台股＋美股）`
2. 將 `/history` 加入 `_BOT_COMMANDS`，說明文字：`查詢歷史報告（互動選單）`

### 非功能需求

- `_register_bot_commands()` 的實作邏輯不得改動
- 不得修改 webhook dispatcher 邏輯、`_HELP_TEXT`、任何 service/repo 層程式碼
- `_BOT_COMMANDS` 的指令順序：`q`, `pnl`, `us`, `tw`, `history`, `help`

---

## 技術方案

### 唯一修改點

檔案：`src/fastapistock/main.py`

修改 `_BOT_COMMANDS` 串列，從：

```python
_BOT_COMMANDS = [
    {'command': 'q', 'description': '本季投資達成率'},
    {'command': 'us', 'description': '美股報價，例：/us AAPL,TSLA'},
    {'command': 'tw', 'description': '台股報價，例：/tw 0050,2330'},
    {'command': 'help', 'description': '顯示所有指令說明'},
]
```

改為：

```python
_BOT_COMMANDS = [
    {'command': 'q', 'description': '本季投資達成率'},
    {'command': 'pnl', 'description': '投資組合未實現損益（台股＋美股）'},
    {'command': 'us', 'description': '美股報價，例：/us AAPL,TSLA'},
    {'command': 'tw', 'description': '台股報價，例：/tw 0050,2330'},
    {'command': 'history', 'description': '查詢歷史報告（互動選單）'},
    {'command': 'help', 'description': '顯示所有指令說明'},
]
```

### 次要修改：架構文件更新

檔案：`docs/architecture.md`

移除 Note（`/pnl 與 /history 透過 webhook 支援，但未顯示於 bot menu`），
並更新 `setMyCommands` 標籤為 `(q/pnl/us/tw/history/help)`。

---

## User Stories

### US-1

As a 投資人,
I want to see `/pnl` in the Telegram command quick-select menu,
so that I can tap it directly without typing the full command.

**Acceptance Criteria:**
- Given Bot 已啟動（`_register_bot_commands` 執行完成）
- When 使用者在 Telegram 輸入 `/`
- Then `/pnl — 投資組合未實現損益（台股＋美股）` 出現在快速選單中

### US-2

As a 投資人,
I want to see `/history` in the Telegram command quick-select menu,
so that I can discover and trigger the interactive history report flow easily.

**Acceptance Criteria:**
- Given Bot 已啟動（`_register_bot_commands` 執行完成）
- When 使用者在 Telegram 輸入 `/`
- Then `/history — 查詢歷史報告（互動選單）` 出現在快速選單中

---

## 影響範圍確認

| 元件 | 影響 | 說明 |
|------|------|------|
| `src/fastapistock/main.py` | 修改 | 僅新增兩個 dict entry 至 `_BOT_COMMANDS` |
| `src/fastapistock/routers/webhook.py` | 無 | 指令已實作，不動 |
| `src/fastapistock/services/` | 無 | 所有 service 不動 |
| `docs/architecture.md` | 更新 | 序列圖標籤同步修正 |
| 測試 | 新增 | 驗證 `_BOT_COMMANDS` 包含 6 個指令 |

---

## Edge Cases

| 情境 | 處理方式 |
|------|----------|
| `TELEGRAM_TOKEN` 未設定 | 現有邏輯已處理：跳過 `setMyCommands`，log warning，非 fatal |
| `setMyCommands` HTTP 呼叫失敗 | 現有邏輯已處理：log warning，非 fatal，應用正常啟動 |
| 重複部署（idempotency） | `setMyCommands` 為覆蓋語意，重複呼叫無副作用 |

---

## Out of Scope

- 修改 `/help` 回覆文字（已正確，不需動）
- 修改 webhook dispatcher 邏輯
- 新增任何 service/repository 程式碼
- 新增或修改 API 路由
