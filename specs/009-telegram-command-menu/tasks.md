# Tasks — 009 新增 /pnl 與 /history 到 Telegram Bot 快速選單

## 依賴關係

```
T1 → T2 → T3
```

---

## T1 — 修改 `_BOT_COMMANDS`

**檔案**：`src/fastapistock/main.py`

**描述**：在 `_BOT_COMMANDS` 串列中新增 `pnl` 與 `history` 兩個 entry。

**AC**：
- [ ] `_BOT_COMMANDS` 長度為 6
- [ ] 第 2 個 entry 為 `{'command': 'pnl', 'description': '投資組合未實現損益（台股＋美股）'}`
- [ ] 第 5 個 entry 為 `{'command': 'history', 'description': '查詢歷史報告（互動選單）'}`
- [ ] `help` 仍為最後一個 entry
- [ ] `_register_bot_commands()` 函式本體及 `_lifespan` 呼叫點均不變

---

## T2 — 更新 `docs/architecture.md` 序列圖

**檔案**：`docs/architecture.md`

**描述**：同步更新 Mermaid 序列圖，移除已過時的 Note。

**AC**：
- [ ] `setMyCommands` 標籤包含全部 6 個指令：`q/pnl/us/tw/history/help`
- [ ] 舊 Note（`/pnl 與 /history 透過 webhook 支援，但未顯示於 bot menu`）已移除
- [ ] 其餘序列圖內容不變

---

## T3 — 撰寫單元測試

**檔案**：`tests/test_spec009_bot_commands.py`（新增）

**測試項目**：
1. `_BOT_COMMANDS` 長度等於 6
2. command 欄位集合等於 `{'q', 'pnl', 'us', 'tw', 'history', 'help'}`
3. 每個 entry 的 `description` 為非空字串
4. `help` 為最後一個 entry（`_BOT_COMMANDS[-1]['command'] == 'help'`）
5. `pnl` 的 description 包含「損益」
6. `history` 的 description 包含「歷史」

**AC**：
- [ ] 所有 6 項測試通過
- [ ] `uv run pytest tests/test_spec009_bot_commands.py -v` 無 FAILED

---

## 完成定義 (Definition of Done)

- [ ] T1 完成：`main.py` `_BOT_COMMANDS` 包含 6 個 entry
- [ ] T2 完成：`docs/architecture.md` 序列圖已同步
- [ ] T3 完成：測試通過
- [ ] `uv run ruff check . --fix && uv run ruff format .` 通過
- [ ] `uv run mypy src/` 無新增錯誤
- [ ] `uv run pre-commit run --all-files` 通過
- [ ] 現有測試套件全部通過（無回歸）
