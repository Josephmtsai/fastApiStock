# Tasks — 008 月報改為每月第一個周日觸發

## Task 清單

### T1 — 修改 scheduler.py 月報 trigger

**檔案**：`src/fastapistock/scheduler.py`

**修改前**（第 156-162 行）：
```python
scheduler.add_job(
    partial(run_report_pipeline, report_type='monthly', trigger='cron'),
    trigger=CronTrigger(day=1, hour=21, minute=0, timezone=str(_TZ)),
    id='monthly_report',
    name='Monthly portfolio report',
    replace_existing=True,
)
```

**修改後**：
```python
scheduler.add_job(
    partial(run_report_pipeline, report_type='monthly', trigger='cron'),
    trigger=CronTrigger(day_of_week='sun', day='1-7', hour=21, minute=0, timezone=str(_TZ)),
    id='monthly_report',
    name='Monthly portfolio report (first Sunday)',
    replace_existing=True,
)
```

**驗收**：
- `CronTrigger` 參數正確
- job `name` 更新為 `'Monthly portfolio report (first Sunday)'`

---

### T2 — 撰寫單元測試

**檔案**：`tests/test_scheduler.py`（新增或補充現有）

測試項目：
1. `CronTrigger(day_of_week='sun', day='1-7')` 應在每月第一個周日觸發
2. 確認月報 job 不再有 `day=1` 的設定
3. 確認週報 job（`day_of_week='sun'`）設定未被修改

---

## 完成定義 (Definition of Done)

- [ ] T1 完成，`scheduler.py` 已更新
- [ ] T2 完成，新測試通過
- [ ] `uv run ruff check . --fix && uv run ruff format .` 通過
- [ ] `uv run mypy src/` 無新增錯誤
- [ ] `uv run pre-commit run --all-files` 通過
