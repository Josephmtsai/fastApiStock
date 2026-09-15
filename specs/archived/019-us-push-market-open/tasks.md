# Tasks 019 — 美股定時推播改為美東開盤（DST-aware）起算

依 `specs/019-us-push-market-open/spec.md` 實作。
分支：`feature/019-us-push-market-open`（自 `main` 建立，禁止直接改 main）。

---

## T0 建立 feature branch
- [ ] **目標**：自 `main` 建立 `feature/019-us-push-market-open`。
- **指令**：`git checkout main && git checkout -b feature/019-us-push-market-open`
- **驗收**：`git branch --show-current` 輸出 `feature/019-us-push-market-open`。

## T1 重寫 `is_us_market_window`（ET 判定、半開區間）
- [ ] **目標**：依 spec「Data Contracts」重寫 `is_us_market_window` 本體與 docstring。
- **涉及檔案**：`src/fastapistock/scheduler.py`（L45–63；module 常數加在 `_TZ` 之後）
- **要求**：
  - 新增 module 常數 `_ET_TZ = ZoneInfo('America/New_York')`、
    `_US_OPEN_MINUTES = 9 * 60 + 30`、`_US_CLOSE_MINUTES = 16 * 60`。
  - naive datetime 以 `now.replace(tzinfo=_TZ)` 視為台北（E5）。
  - `et = now.astimezone(_ET_TZ)`；`et.weekday() > 4` → False；
    `_US_OPEN_MINUTES <= et.hour * 60 + et.minute < _US_CLOSE_MINUTES`。
  - 函式簽章 `is_us_market_window(now: datetime) -> bool` 不變。
  - docstring 依 spec Data Contracts 更新（Google Style，說明 ET 半開區間與
    夏/冬令台北對應）。
  - 不跨模組 import `us_stock_repo._ET_TZ`；不動其他函式。
- **驗收（AC-1.1–1.4、AC-2.1–2.3、AC-3.1–3.4、E1–E6）**：
  - spec G1 真值表 S1–S12、W1–W11、D1–D15、N1 逐筆成立。
  - `uv run mypy src/` 無新增錯誤；`uv run ruff check .` 無新增警告。

## T2 重寫 `TestUsMarketWindow` + 新增 `_previous_us_trading_date` 冬令回歸測試
- [ ] **目標**：把 `tests/test_scheduler.py::TestUsMarketWindow`（L84–124）改為
  參數化真值表；新增一筆 `_previous_us_trading_date` 回歸測試。
- **涉及檔案**：`tests/test_scheduler.py`
- **要求**：
  - 刪除 L84–124 既有 12 個測試（見 spec Affected Tests），改為
    `@pytest.mark.parametrize('now, expected, reason', [...])` 單一測試
    （或依 夏令 / 冬令 / DST 切換 / naive 分 4 個參數化測試，擇一），
    資料集必須逐筆對應 G1 的 39 筆，`reason` 字串含 ET 時間便於失敗時閱讀。
  - datetime 一律 `datetime(Y, M, D, h, m, tzinfo=_TZ)`（naive 案例除外），
    不使用 `_dt` helper（基準只涵蓋夏令）。`_dt` 保留給 TW 測試。
  - 在 `TestDailyCloseSnapshots` 新增
    `test_previous_us_trading_date_winter_late_session_uses_prior_close`：
    `_previous_us_trading_date(datetime(2026, 1, 13, 4, 30, tzinfo=_TZ)) == '2026-01-09'`。
  - `TestScheduledPush`、`TestTwMarketWindow` 等其他 class 不改。
- **驗收（AC-1.x、AC-2.x、AC-3.x、AC-4.1、AC-4.2、E8）**：
  - `uv run pytest tests/test_scheduler.py -v` 全綠。
  - 收集到的 `TestUsMarketWindow` 案例數 >= 39。
  - `git diff tests/test_scheduler.py` 只觸及 `TestUsMarketWindow` 與
    `TestDailyCloseSnapshots` 新增一筆。

## T3 文件更新
- [ ] **目標**：更新 window 描述。
- **涉及檔案**：`docs/architecture.md`（L212、L224）、`.env.example`（L23）
- **要求**：逐字採用 spec Golden Sample G2 的三段文字；不改動其他行。
- **驗收**：
  - `docs/architecture.md`、`.env.example` 內不再出現 `17:00`。
  - `rg -n "09:30–16:00 ET" docs/architecture.md` 命中 2 行；
    `rg -n "09:30-16:00 ET" .env.example` 命中 1 行。
  - mermaid 區塊仍為合法語法（label 內只用 `<br/>`、`/`、`–`，無未轉義的 `|`）。

## T4 全量驗證 + Conventional Commit + handoff-dev.json
- [ ] **目標**：品質門檻全過後提交，並產出 handoff。
- **指令**：
  1. `uv run ruff check . --fix && uv run ruff format .`
  2. `uv run mypy src/`
  3. `uv run pytest`（全套，含覆蓋率設定）
  4. `uv run pre-commit run --all-files`
  5. `git add -A && git commit -m "feat(scheduler): start US push at ET 09:30 open, DST-aware"`
     （可拆為 `feat:` + `test:` + `docs:` 多個 commit；皆需符合 Conventional Commits）
  6. 寫入 `specs/019-us-push-market-open/handoff-dev.json`：
     ```json
     {
       "from": "developer",
       "to": "qa",
       "feature": "019-us-push-market-open",
       "status": "ready",
       "summary": "...",
       "changed_files": [
         "src/fastapistock/scheduler.py",
         "tests/test_scheduler.py",
         "docs/architecture.md",
         ".env.example"
       ],
       "ac_ref": "specs/019-us-push-market-open/tasks.md"
     }
     ```
- **驗收**：
  - 1–4 全部 0 error / 0 fail；無新增 `# noqa`、無 `Any`、無 `print()`。
  - `git log --oneline main..HEAD` 每筆皆為 Conventional Commit。
  - `handoff-dev.json` 的 `changed_files` 與 `git diff --name-only main..HEAD`
    一致（spec 目錄下的 handoff 檔可不列）。
  - 回報 orchestrator 可 spawn **codex-reviewer**（非直接 QA）。

---

## Acceptance Criteria（QA 直接驗證清單）

以下每條皆可用 `uv run pytest tests/test_scheduler.py -v -k <keyword>` 或
`uv run python -c` 直接呼叫 `is_us_market_window` 驗證。

| AC | Given（台北時間，`tzinfo=ZoneInfo('Asia/Taipei')`）| When | Then |
|---|---|---|---|
| AC-1.1 | `datetime(2026, 7, 6, 21, 30)` | `is_us_market_window` | `True` |
| AC-1.2 | `datetime(2026, 7, 6, 17, 0)`、`datetime(2026, 7, 6, 21, 29)` | 同上 | 皆 `False` |
| AC-1.3 | `datetime(2026, 1, 12, 22, 30)` | 同上 | `True` |
| AC-1.4 | `datetime(2026, 1, 12, 21, 30)`、`datetime(2026, 1, 12, 17, 0)` | 同上 | 皆 `False` |
| AC-2.1 | `datetime(2026, 1, 13, 4, 30)`、`datetime(2026, 1, 13, 4, 59)` | 同上 | 皆 `True` |
| AC-2.2 | `datetime(2026, 1, 13, 5, 0)`、`datetime(2026, 7, 7, 4, 0)` | 同上 | 皆 `False` |
| AC-2.3 | `datetime(2026, 7, 7, 3, 59)` | 同上 | `True` |
| AC-3.1 | `datetime(2026, 7, 11, 22, 0)`、`datetime(2026, 7, 12, 22, 0)`、`datetime(2026, 7, 13, 3, 0)` | 同上 | 皆 `False` |
| AC-3.2 | `datetime(2026, 7, 11, 3, 30)`、`datetime(2026, 1, 17, 4, 30)` | 同上 | 皆 `True` |
| AC-3.3 | `(2026, 3, 6, 21, 30)`→F、`(2026, 3, 6, 22, 30)`→T、`(2026, 3, 9, 21, 30)`→T、`(2026, 3, 9, 21, 29)`→F | 同上 | 如左 |
| AC-3.4 | `(2026, 10, 30, 21, 30)`→T、`(2026, 11, 2, 21, 30)`→F、`(2026, 11, 2, 22, 30)`→T、`(2026, 11, 3, 4, 30)`→T、`(2026, 11, 3, 5, 0)`→F | 同上 | 如左 |
| AC-4.1 | `tests/test_scheduler.py::TestScheduledPush` 未被修改（`git diff main..HEAD -- tests/test_scheduler.py` 不含該 class 的行）| `uv run pytest tests/test_scheduler.py -k TestScheduledPush` | 4 passed |
| AC-4.2 | 全套測試 | `uv run pytest` | 全綠；`tests/test_us_stock_repo.py`、`tests/test_telegram_formatter.py` 無改動 |
| E5 | naive `datetime(2026, 7, 6, 21, 30)` | `is_us_market_window` | `True` |
| E8 | `datetime(2026, 1, 13, 4, 30, tzinfo=_TZ)` | `_previous_us_trading_date` | `'2026-01-09'` |
| DOC | `rg -n "17:00" docs/architecture.md .env.example` | 執行 | 無命中 |

---

## AC 對照表

| Task | 對應 AC / Edge Case |
|---|---|
| T0 | —（流程要求）|
| T1 | AC-1.1–1.4、AC-2.1–2.3、AC-3.1–3.4、E1–E6 |
| T2 | AC-1.x–3.x（以測試固定）、AC-4.1、AC-4.2、E5、E8 |
| T3 | DOC |
| T4 | AC-4.2（全套）、品質門檻 |

## 執行順序

T0 → T1 → T2（T1 未完成前 T2 必紅，屬預期）→ T3（可與 T2 平行）→ T4。
