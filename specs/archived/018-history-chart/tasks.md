# Tasks 018 — /history 圖表化與結果頁快速按鈕

依 `specs/018-history-chart/spec.md` 實作。分支:`feature/018-history-chart`。

---

## T0 建立 feature branch
- **目標**:自 main 建立 `feature/018-history-chart`,禁止直接改 main。
- **指令**:`git checkout -b feature/018-history-chart`
- **驗收**:`git branch --show-current` 為 `feature/018-history-chart`。

## T1 加入 matplotlib 依賴
- **目標**:`uv add matplotlib`(進 `[project].dependencies`,非 dev group)。
- **涉及檔案**:`pyproject.toml`、`uv.lock`
- **驗收**:
  - `uv run python -c "from matplotlib.backends.backend_agg import FigureCanvasAgg"` 成功
  - `uv sync --frozen` 可重現(lock 已更新)
  - 不修改 Dockerfile(slim + wheel 即可用)

## T2 chart_service 新模組 + 單元測試
- **目標**:實作 `render_symbol_chart` / `render_summary_chart`(spec Data Contracts)。
- **涉及檔案**:`src/fastapistock/services/chart_service.py`(新)、
  `tests/test_chart_service.py`(新)
- **要求**:
  - 只用 OO API(`Figure` + `FigureCanvasAgg`),禁止 import pyplot、禁止 `matplotlib.use()`
  - 空 list raise `ValueError`;Decimal→float;marker='o';ASCII 標籤(spec 表格)
  - `render_summary_chart` 支援 `market='TW'|'US'|'ALL'`(ALL=雙 y 軸)
  - 函式 ≤50 行(抽 `_to_float_series` / `_fig_to_png` helper);mypy strict 無 Any
    (matplotlib stub 缺口允許 `# type: ignore[...]` + 註釋)
- **驗收(AC 對照:AC-1.1 圖元素、AC-2.1、AC-2.2、E2–E5)**:
  - 回傳 bytes 以 `\x89PNG\r\n\x1a\n` 開頭
  - 空 rows/summaries → ValueError
  - 單點、avg_cost None、pnl_pct None、單期 summary 皆不拋錯且回有效 PNG
  - 測試無 GUI、無網路

## T3 telegram_service.send_photo + 單元測試
- **目標**:新增 `send_photo(chat_id, photo, caption=None) -> bool`。
- **涉及檔案**:`src/fastapistock/services/telegram_service.py`、
  `tests/test_telegram_send_photo.py`(新,或併入既有 telegram 測試檔)
- **要求**:multipart(`files={'photo': ('chart.png', photo, 'image/png')}`)、
  `_REQUEST_TIMEOUT`、無 token→False、HTTPStatusError/RequestError→log+False,
  結構比照 `reply_to_chat`;不動既有函式。
- **驗收(E6、E12)**:
  - mock httpx.post 驗證 URL(`/sendPhoto`)、data/files payload、caption 有值才帶
  - 2xx→True;HTTPStatusError→False;RequestError→False;無 token→False
  - 全程 mock,無真實請求

## T4 history_handler:g/r step + 結果頁按鈕列 + 測試
- **目標**:實作 `_step_send_chart`、`_step_reset`、
  `_result_keyboard_symbol` / `_result_keyboard_summary`,
  `_render_symbol` / `_render_summary` 附 reply_markup,
  `handle_callback` 加 g/r 分支,更新 module docstring grammar。
- **涉及檔案**:`src/fastapistock/services/history_handler.py`、
  `tests/test_history_webhook.py`
- **要求**:
  - grammar:`hist:g:symbol:<market>:<symbol>:<period>`、
    `hist:g:summary:<market|ALL>:<period>`、`hist:r:menu`(3 段,不放寬 len guard)
  - `_step_send_chart`:白名單驗證→查 repo→空則文字告知→
    `try/except Exception` 包渲染→send_photo→False 則文字告知;不拋出
  - `_step_reset`:edit 為 type menu(重用 `_send_type_menu` 的 keyboard 定義,
    抽共用 helper 避免重複)
  - 圖表為新訊息,原結果訊息不動;每函式 ≤50 行
- **驗收(AC-1.1、AC-1.2、AC-2.1、AC-2.2、AC-3.1、AC-4.1、E1、E7、E9、E10)**:
  - **先修壞測試**:`test_period_summary_renders_results` 的
    `'reply_markup' not in kwargs` 改為驗證按鈕列
  - g step:sendPhoto 被呼叫、photo bytes 為 PNG、edit_message_text 未被呼叫
  - g step 空資料 / 渲染例外(mock render 拋 RuntimeError)/ send_photo False
    → reply_to_chat 對應文字,webhook 200
  - toggle:`hist:p:symbol:TW:2330:weekly` 重渲染且按鈕帶 weekly/切換月報
  - `hist:r:menu`:edit 為 type menu keyboard;`hist:r`(2 段)被 guard 擋下
  - 既有 t/m/s/p 測試全數通過(舊流程不受影響)

## T5 文字捷徑按鈕列 + 測試
- **目標**:`handle_text_command` 成功回覆附相同按鈕列
  (market=`rows[0].market`、period=`'monthly'`);查無資料/用法錯誤路徑不變。
- **涉及檔案**:`src/fastapistock/services/history_handler.py`、
  `tests/test_history_webhook.py`
- **驗收(AC-5.1)**:
  - `/history 2330` 回覆帶 reply_markup 含 `hist:g:symbol:TW:2330:monthly`
  - 文字內容與既有測試斷言不變;不自動 sendPhoto
  - `test_symbol_only_auto_detects_market` / `test_us_prefix_calls_repo_with_us`
    增補 markup 斷言後通過

## T6 全量驗證 + commit + handoff-dev.json
- **目標**:品質門檻全過並產出 handoff。
- **指令**:
  1. `uv run ruff check . --fix && uv run ruff format .`
  2. `uv run mypy src/`
  3. `uv run pytest`(覆蓋率 ≥80%)
  4. `uv run pre-commit run --all-files`
  5. Conventional Commit(如 `feat: add /history chart rendering and result-page quick buttons`)
  6. 產出 `specs/018-history-chart/handoff-dev.json`(changed_files 完整列出,
     status: ready,ac_ref 指向本檔)
- **驗收**:四項指令零錯誤;commit 在 feature branch;不 merge、不 deploy;
  告知 orchestrator spawn **codex-reviewer**(非直接 QA)。

---

## AC 對照表

| AC / Edge | 驗證位置 |
|-----------|---------|
| AC-1.1 | T2(圖元素)+ T4(g step 送圖) |
| AC-1.2 / E1 | T4 |
| AC-2.1 / AC-2.2 | T2 + T4 |
| AC-3.1 | T4(toggle) |
| AC-4.1 | T4(reset) |
| AC-5.1 | T5 |
| E2–E5 | T2 |
| E6 / E12 | T3 |
| E7 / E9 / E10 | T4 |
| E8 | T4(grammar 常數,測試斷言 callback_data 長度 <64) |
| E11 | T2 |
