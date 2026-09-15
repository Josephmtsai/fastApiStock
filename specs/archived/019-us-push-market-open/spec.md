# Spec 019 — 美股定時推播改為美東開盤（DST-aware）起算

分支：`feature/019-us-push-market-open`（自 `main` 建立，禁止直接改 main）

---

## Overview

`is_us_market_window` 改為把 `now` 轉成 `America/New_York` 後，以美東常規盤
Mon–Fri `09:30 <= t < 16:00` ET 判定，取消現行台北 17:00 起算的盤前推播；
函式簽章與呼叫端不變。

---

## 背景與問題

- 現行 `src/fastapistock/scheduler.py::is_us_market_window`（L45–63）：
  Mon–Fri 17:00 台北以後 → True；Tue–Sat 00:00–04:00 台北 → True。
- 17:00 台北 = 05:00 EDT / 04:00 EST，是盤前時段；盤前價幾乎不動，
  每 30 分鐘推播沒有資訊價值。
- 現行規則是固定台北時間，冬令時美股 16:00 EST 收盤 = 05:00 台北，
  現行 window 在 04:00 台北就結束，最後一小時盤中沒有推播。
- `repositories/us_stock_repo.py` 已有 `_ET_TZ = ZoneInfo('America/New_York')`
  以 ET wall-clock 判斷盤前（04:00–09:30 ET），證明 zoneinfo 在本專案可用。

---

## User Stories

### US-1 只在美股常規盤時段收到定時推播

As a 投資人（TELEGRAM_USER_ID 持有者），
I want to 只在美股常規盤（09:30–16:00 美東）期間每 30 分鐘收到美股定時推播，
so that 不再收到盤前價格幾乎不變的無意義訊息。

**AC-1.1（夏令開盤起算）**
- Given 台北時間為夏令期間的週一 21:30（= 09:30 EDT）
- When 排程 tick 呼叫 `is_us_market_window(now)`
- Then 回傳 `True`

**AC-1.2（夏令盤前不推）**
- Given 台北時間為夏令期間的週一 17:00（= 05:00 EDT）或 21:29（= 09:29 EDT）
- When 呼叫 `is_us_market_window(now)`
- Then 回傳 `False`

**AC-1.3（冬令開盤起算）**
- Given 台北時間為冬令期間的週一 22:30（= 09:30 EST）
- When 呼叫 `is_us_market_window(now)`
- Then 回傳 `True`

**AC-1.4（冬令時夏令開盤時刻仍是盤前）**
- Given 台北時間為冬令期間的週一 21:30（= 08:30 EST）或 17:00（= 04:00 EST）
- When 呼叫 `is_us_market_window(now)`
- Then 回傳 `False`

### US-2 推播涵蓋到收盤前、不含收盤後

As a 投資人，
I want to 冬令時也能收到台北 04:00–04:59 這段（= 15:00–15:59 EST）的盤中推播，
且 16:00 ET 收盤後不再推播，
so that 冬令最後一小時盤中不漏推，收盤後也不重複推播（收盤報告另有
`daily_pnl_us` cron 負責）。

**AC-2.1（冬令收盤前最後一段）**
- Given 台北時間為冬令期間的週二 04:30 或 04:59（= 週一 15:30 / 15:59 EST）
- When 呼叫 `is_us_market_window(now)`
- Then 回傳 `True`

**AC-2.2（收盤時刻排除，半開區間）**
- Given 台北時間為冬令週二 05:00（= 週一 16:00 EST）或夏令週二 04:00
  （= 週一 16:00 EDT）
- When 呼叫 `is_us_market_window(now)`
- Then 回傳 `False`

**AC-2.3（夏令收盤前最後一分鐘）**
- Given 台北時間為夏令週二 03:59（= 週一 15:59 EDT）
- When 呼叫 `is_us_market_window(now)`
- Then 回傳 `True`

### US-3 週末與 DST 切換日正確

As a 投資人，
I want to 週末（以美東日曆為準）不收到推播，且 DST 切換前後的第一個交易日
使用正確的開盤時刻，
so that 換季當週不會提早一小時開始推盤前、或晚一小時漏推。

**AC-3.1（美東週末排除）**
- Given 台北週六 22:00（= 週六 10:00 ET）、台北週日 22:00（= 週日 10:00 ET）、
  台北週一 03:00（= 週日 15:00 EDT）
- When 呼叫 `is_us_market_window(now)`
- Then 皆回傳 `False`

**AC-3.2（週五盤延伸到台北週六凌晨）**
- Given 台北夏令週六 03:30（= 週五 15:30 EDT）、台北冬令週六 04:30
  （= 週五 15:30 EST）
- When 呼叫 `is_us_market_window(now)`
- Then 皆回傳 `True`

**AC-3.3（春季 DST 切換：2026-03-08 週日）**
- Given 台北 2026-03-06（五）21:30 → `False`（08:30 EST）；
  2026-03-06 22:30 → `True`（09:30 EST）；
  2026-03-09（一）21:30 → `True`（09:30 EDT）；
  2026-03-09 21:29 → `False`
- When 逐一呼叫 `is_us_market_window(now)`
- Then 結果如上

**AC-3.4（秋季 DST 切換：2026-11-01 週日）**
- Given 台北 2026-10-30（五）21:30 → `True`（09:30 EDT）；
  2026-11-02（一）21:30 → `False`（08:30 EST）；
  2026-11-02 22:30 → `True`（09:30 EST）；
  2026-11-03（二）04:30 → `True`（15:30 EST）；2026-11-03 05:00 → `False`
- When 逐一呼叫 `is_us_market_window(now)`
- Then 結果如上

### US-4 既有呼叫端與其他排程不受影響

As a 維護者，
I want to `is_us_market_window` 簽章與 `_scheduled_push` 流程不變，
so that mock 這個函式的既有測試與其他 cron job 完全不動。

**AC-4.1**
- Given `tests/test_scheduler.py::TestScheduledPush`（L195–258）以 `patch`
  取代 `is_us_market_window`
- When 執行 `uv run pytest tests/test_scheduler.py`
- Then 該 class 4 個測試不修改即通過

**AC-4.2**
- Given `is_tw_market_window`、`build_scheduler` 所有 job 定義、
  `_previous_us_trading_date`、`push_us_stocks`、`_fetch_premarket_price`
- When 執行全套測試
- Then 不變、既有測試通過

---

## 方案評估與選定

| | (a) 全部改用 ET 判定 Mon–Fri 09:30–16:00 ET | (b) 只改晚間起點為 DST-aware，保留台北 Tue–Sat 00:00–04:00 分支 |
|---|---|---|
| 邏輯 | 單一：轉 ET → 週幾 + 分鐘區間 | 兩套時區混用：起點看 ET、終點看台北 |
| 冬令收盤 | 05:00 台北自然涵蓋到 04:59 | 04:00 台北就切掉，最後一小時漏推（與現況相同缺陷） |
| DST 切換 | zoneinfo 自動處理 | 起點自動、終點仍固定 |
| 測試 | 以 ET 語意直接推導 | 需同時推導兩套時區 |

**選定 (a)**。理由：邏輯單一（KISS）、冬令收盤自然正確、DST 交由 zoneinfo。

### 邊界定義：半開區間 `09:30 <= t_ET < 16:00`

理由（依重要性）：

1. **`_previous_us_trading_date` 相容性**（scheduler.py L180–186，本次不動）：
   它以 `local.hour <= 4` 判斷「仍在前一日美東盤中」。若採 inclusive
   `<= 16:00`，冬令 16:00 EST = 台北 05:00，`hour == 5` 會落到
   `_previous_weekday(local.date())`，把「當日盤」自己的日期（如週一）當成
   baseline，PnL delta 會拿 `us_daily_close_snapshot`（台北 04:10 = 15:10 EST
   盤中價）當基準，數字錯誤。半開區間下所有 in-window tick 的台北 hour 皆在
   {21, 22, 23, 0, 1, 2, 3, 4}，`hour <= 4` 啟發式全部成立，不需要動該函式。
2. 16:00 ET 常規盤已結束，收盤報告由 `daily_pnl_us` cron 負責；定時推播的
   目的是盤中快照。
3. `IntervalTrigger(minutes=30)` 無 `start_date`，tick 相對程序啟動時間，並非
   對齊 :00/:30，恰好落在 16:00 ET 的機率極低；邊界主要影響測試語意。

### 台北 ↔ 美東對照表（Golden Sample 之一）

| 項目 | 夏令 EDT（UTC−4，台北 −12h）<br/>2026-03-08 ～ 2026-10-31 | 冬令 EST（UTC−5，台北 −13h）<br/>2026-11-01 ～ 2027-03-13、2026-01-01 ～ 2026-03-07 |
|---|---|---|
| 開盤 09:30 ET | 當日 21:30 台北 | 當日 22:30 台北 |
| 收盤 16:00 ET | 次日 04:00 台北 | 次日 05:00 台北 |
| 推播 window（台北）| Mon–Fri 21:30–23:59 + Tue–Sat 00:00–03:59 | Mon–Fri 22:30–23:59 + Tue–Sat 00:00–04:59 |
| 舊規則（台北）| Mon–Fri 17:00–23:59 + Tue–Sat 00:00–04:00 | 同左（無 DST 概念）|
| 差異 | 少推 17:00–21:29（盤前）、少推 04:00 那一分鐘 | 少推 17:00–22:29（盤前）、**多推 04:01–04:59（盤中）** |

2026 年 DST：3/8（日）02:00 開始、11/1（日）02:00 結束（美國第二個週日 3 月 /
第一個週日 11 月）。切換皆在週日，因此週一是第一個套用新 offset 的交易日。

---

## Modules

| 模組 / 檔案 | 異動 | 說明 |
|---|---|---|
| `src/fastapistock/scheduler.py` | 修改 | 新增 `_ET_TZ = ZoneInfo('America/New_York')`、`_US_OPEN_MINUTES = 9 * 60 + 30`、`_US_CLOSE_MINUTES = 16 * 60` module 常數；重寫 `is_us_market_window`（L45–63）本體與 docstring。其他函式不動。 |
| `tests/test_scheduler.py` | 修改 | 重寫 `TestUsMarketWindow`（L84–124）；新增 `_previous_us_trading_date` 冬令回歸測試。其餘 class 不動。 |
| `docs/architecture.md` | 修改 | L212 文字、L224 mermaid 標籤更新 window 描述。 |
| `.env.example` | 修改 | L23 註解由 `Mon–Fri 17:00–04:00 next day Taipei` 改為 ET 描述（見 Golden Sample）。 |
| `src/fastapistock/repositories/us_stock_repo.py` | 不動 | `_fetch_premarket_price`、`_ET_TZ` 保持私有；scheduler 自行宣告常數，不跨模組 import 私有名稱。 |
| `src/fastapistock/services/telegram_service.py` | 不動 | `[盤前]` 標籤邏輯照舊。 |
| `scheduler.py` 其他 cron（`daily_pnl_us` 04:05、`us_daily_close_snapshot` 04:10）| 不動 | 見 Out of Scope。 |

---

## Data Contracts

### `is_us_market_window(now: datetime) -> bool`（簽章不變）

```python
_ET_TZ = ZoneInfo('America/New_York')
_US_OPEN_MINUTES = 9 * 60 + 30   # 09:30 ET
_US_CLOSE_MINUTES = 16 * 60      # 16:00 ET (exclusive)


def is_us_market_window(now: datetime) -> bool:
    """Return True when *now* falls in the US regular-session push window.

    Window: Monday–Friday 09:30 <= t < 16:00 America/New_York (DST-aware).
    In Taipei terms this is 21:30–03:59 (next day) during US daylight time
    and 22:30–04:59 (next day) during US standard time. Weekday is judged
    on the Eastern-Time calendar, so Saturday 03:00 Taipei (= Friday
    afternoon ET) is inside and Monday 03:00 Taipei (= Sunday ET) is not.

    Args:
        now: Current datetime in Asia/Taipei (timezone-aware). A naive
            datetime is treated as Asia/Taipei wall-clock time.

    Returns:
        True if a US stock push should be sent.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=_TZ)
    et = now.astimezone(_ET_TZ)
    if et.weekday() > 4:  # Saturday=5, Sunday=6 on the ET calendar
        return False
    minutes = et.hour * 60 + et.minute
    return _US_OPEN_MINUTES <= minutes < _US_CLOSE_MINUTES
```

- 輸入：`datetime`，tz-aware（Asia/Taipei，實務上 `_scheduled_push` 傳
  `datetime.now(_TZ)`）。任何 tz-aware datetime 皆可正確轉換。
- 輸出：`bool`。
- 副作用：無；不打網路、不讀 config。
- 秒數忽略（沿用現行 `hour*60+minute` 慣例）。

---

## API Design

無新增 HTTP 路由。

---

## Golden Sample

### G1 真值表（供 QA 逐筆比對；台北時間 → ET → 期望）

| # | 台北時間（Asia/Taipei） | 對應 ET | 期望 | 說明 |
|---|---|---|---|---|
| S1 | 2026-07-06 Mon 17:00 | Mon 05:00 EDT | False | 舊規則 True → 本次核心變更 |
| S2 | 2026-07-06 Mon 21:29 | Mon 09:29 EDT | False | 開盤前一分鐘 |
| S3 | 2026-07-06 Mon 21:30 | Mon 09:30 EDT | True | 夏令開盤 |
| S4 | 2026-07-07 Tue 00:00 | Mon 12:00 EDT | True | 跨台北午夜 |
| S5 | 2026-07-07 Tue 03:59 | Mon 15:59 EDT | True | 夏令收盤前最後一分鐘 |
| S6 | 2026-07-07 Tue 04:00 | Mon 16:00 EDT | False | 收盤時刻（半開）；舊規則 True |
| S7 | 2026-07-10 Fri 23:00 | Fri 11:00 EDT | True | |
| S8 | 2026-07-11 Sat 03:30 | Fri 15:30 EDT | True | 週五盤延伸 |
| S9 | 2026-07-11 Sat 04:00 | Fri 16:00 EDT | False | 舊規則 True |
| S10 | 2026-07-11 Sat 22:00 | Sat 10:00 EDT | False | 週末 |
| S11 | 2026-07-12 Sun 22:00 | Sun 10:00 EDT | False | 週末 |
| S12 | 2026-07-13 Mon 03:00 | Sun 15:00 EDT | False | ET 仍是週日 |
| W1 | 2026-01-12 Mon 17:00 | Mon 04:00 EST | False | 舊規則 True |
| W2 | 2026-01-12 Mon 21:30 | Mon 08:30 EST | False | 夏令開盤時刻在冬令仍是盤前 |
| W3 | 2026-01-12 Mon 22:29 | Mon 09:29 EST | False | |
| W4 | 2026-01-12 Mon 22:30 | Mon 09:30 EST | True | 冬令開盤 |
| W5 | 2026-01-13 Tue 04:30 | Mon 15:30 EST | True | 舊規則 False → 冬令多推 |
| W6 | 2026-01-13 Tue 04:59 | Mon 15:59 EST | True | |
| W7 | 2026-01-13 Tue 05:00 | Mon 16:00 EST | False | 收盤時刻（半開） |
| W8 | 2026-01-17 Sat 04:30 | Fri 15:30 EST | True | 週五盤延伸 |
| W9 | 2026-01-17 Sat 05:00 | Fri 16:00 EST | False | |
| W10 | 2026-01-12 Mon 04:00 | Sun 15:00 EST | False | ET 週日 |
| W11 | 2026-01-18 Sun 23:00 | Sun 10:00 EST | False | 週末 |
| D1 | 2026-03-06 Fri 21:30 | Fri 08:30 EST | False | 春季切換前最後交易日 |
| D2 | 2026-03-06 Fri 22:30 | Fri 09:30 EST | True | |
| D3 | 2026-03-07 Sat 04:30 | Fri 15:30 EST | True | |
| D4 | 2026-03-07 Sat 05:00 | Fri 16:00 EST | False | |
| D5 | 2026-03-09 Mon 21:29 | Mon 09:29 EDT | False | 切換後第一個交易日 |
| D6 | 2026-03-09 Mon 21:30 | Mon 09:30 EDT | True | |
| D7 | 2026-03-10 Tue 03:59 | Mon 15:59 EDT | True | |
| D8 | 2026-03-10 Tue 04:00 | Mon 16:00 EDT | False | |
| D9 | 2026-10-30 Fri 21:30 | Fri 09:30 EDT | True | 秋季切換前最後交易日 |
| D10 | 2026-10-31 Sat 03:59 | Fri 15:59 EDT | True | |
| D11 | 2026-10-31 Sat 04:00 | Fri 16:00 EDT | False | |
| D12 | 2026-11-02 Mon 21:30 | Mon 08:30 EST | False | 切換後第一個交易日 |
| D13 | 2026-11-02 Mon 22:30 | Mon 09:30 EST | True | |
| D14 | 2026-11-03 Tue 04:30 | Mon 15:30 EST | True | |
| D15 | 2026-11-03 Tue 05:00 | Mon 16:00 EST | False | |
| N1 | naive `datetime(2026, 7, 6, 21, 30)` | 視為台北 → Mon 09:30 EDT | True | E5 |

日期驗證：2026-01-12、2026-04-06、2026-07-06、2026-03-09、2026-11-02 皆為週一；
2026-03-08、2026-11-01 皆為週日（DST 切換日）。

### G2 文件字串

`docs/architecture.md` L212 改為（保留其他文字）：

> 時段由 `is_tw_market_window` 以 Asia/Taipei 判定；`is_us_market_window`
> 先將 now 轉為 America/New_York，以美東常規盤 Mon–Fri 09:30–16:00 ET
>（DST-aware，夏令 21:30–04:00 / 冬令 22:30–05:00 台北）判定。

`docs/architecture.md` L224 改為：

```
    TICK -->|is_us_market_window<br/>Mon–Fri 09:30–16:00 ET<br/>夏令 21:30–04:00 / 冬令 22:30–05:00 台北| PUSH_US[push_us_stocks]
```

`.env.example` L23 改為：

```
# US stock tickers for the US scheduled push (Mon–Fri 09:30–16:00 ET; 21:30–04:00 Taipei in US DST, 22:30–05:00 in standard time)
```

### G3 Log 行為（不變）

`_scheduled_push` 在 window 內仍記錄 `US market window active — pushing`；
window 外無 US 相關 log。無新增 log。

---

## Edge Cases

| # | 情境 | 處理 |
|---|---|---|
| E1 | 台北跨午夜（Tue 00:00–04:59）| 轉 ET 後仍是前一日，以 ET 週幾判定；Tue–Sat 凌晨對應 Mon–Fri ET → 可能 True；Mon 凌晨對應 Sun ET → False |
| E2 | 恰好 16:00 ET | False（半開區間，見「邊界定義」）|
| E3 | 恰好 09:30 ET | True |
| E4 | DST 切換週（3/8、11/1 週日）| zoneinfo 自動處理；切換日本身為週日 → False；週一起用新 offset（G1 D5–D8、D12–D15）|
| E5 | 傳入 naive datetime | 視為 Asia/Taipei wall-clock（`replace(tzinfo=_TZ)`），避免 `astimezone` 以系統時區（Railway 為 UTC）解讀造成 12–13 小時偏差 |
| E6 | 傳入非 Taipei 但 tz-aware 的 datetime（如 UTC）| `astimezone` 正確轉換，結果與同一瞬間的 Taipei 輸入一致；不特別測試，docstring 註明 |
| E7 | 美股假日（如 7/4、感恩節）| 不處理（與現況相同），仍會推播前收價；列 Out of Scope |
| E8 | 冬令 04:01–04:59 台北的新增 tick 觸發 `_safe_send_daily_pnl_delta('US')` | `_previous_us_trading_date` 因 `hour <= 4` 回傳前一交易日（週一 → 週五），baseline 正確；T2 增加回歸測試固定此行為 |
| E9 | tick 落在 window 外 | 不呼叫 `push_us_stocks` 也不呼叫 `_safe_send_daily_pnl_delta('US')`（既有 `_scheduled_push` 流程）|

---

## Affected Tests

### 必壞（需改寫）— `tests/test_scheduler.py::TestUsMarketWindow`（L84–124）

`_dt` helper 基準 2026-04-06（EDT 期間，台北 −12h）。

| 既有測試 | 舊斷言 | 新規則下結果 | 處置 |
|---|---|---|---|
| `test_1700_wednesday_is_in` L85 | 17:00 Wed → True | 05:00 EDT → **False** | 刪除，改為 S1（17:00 → False）|
| `test_0400_thursday_is_in` L91 | 04:00 Thu → True | Wed 16:00 EDT → **False** | 刪除，改為 S5/S6（03:59 True、04:00 False）|
| `test_friday_1700_is_in` L112 | 17:00 Fri → True | 05:00 EDT → **False** | 刪除 |
| `test_saturday_0400_is_in` L122 | 04:00 Sat → True | Fri 16:00 EDT → **False** | 刪除，改為 S8/S9 |

### 仍通過但語意過時（併入重寫）

| 既有測試 | 說明 |
|---|---|
| `test_1659_wednesday_is_out` L88 | 仍 False，但理由已非「17:00 前」；併入 S2 |
| `test_0401_thursday_is_out` L95 | 仍 False（夏令 16:01 EDT）；併入 S6 |
| `test_sunday_2000_is_out` L98 | 仍 False；併入 S11 |
| `test_saturday_0300_is_in` L101 | 仍 True（Fri 15:00 EDT）；併入 S8 |
| `test_saturday_0500_is_out` L105 | 仍 False；併入 S9 |
| `test_monday_0300_is_out` L108 | 仍 False；併入 S12 |
| `test_friday_2300_is_in` L115 | 仍 True；併入 S7 |
| `test_tuesday_0000_is_in` L118 | 仍 True；併入 S4 |

**改寫方式**：整個 class 以 `pytest.mark.parametrize` 重寫，每筆
`(datetime(..., tzinfo=_TZ), expected, reason)`，資料集即 G1 的 S1–S12、W1–W11、
D1–D15、N1（共 39 筆），不再依賴 `_dt` helper（其基準日只涵蓋夏令）。
`_dt` helper 保留給 `TestTwMarketWindow`。

### 需強化（新增）

| 新增測試 | 目的 |
|---|---|
| `TestDailyCloseSnapshots::test_previous_us_trading_date_winter_late_session_uses_prior_close` | `_previous_us_trading_date(datetime(2026, 1, 13, 4, 30, tzinfo=_TZ)) == '2026-01-09'`，固定 E8 行為（半開區間的前提）|

### 不受影響（不修改、必須仍通過）

| 測試 | 原因 |
|---|---|
| `TestTwMarketWindow`、`TestTwMarketWindowTimezone` | `is_tw_market_window` 不動 |
| `TestScheduledPush`（L195–258）| 以 `patch` mock `is_us_market_window`，簽章不變 |
| `TestPushUsStocks`、`TestPushTwStocks` | push 函式不動 |
| `TestBuildScheduler`、`TestMonthlyReportTrigger`、`TestDailyPnlJobTriggers` | job 定義不動 |
| `TestDailyCloseSnapshots` 既有 5 筆 | 相關函式不動 |
| `tests/test_us_stock_repo.py`、`tests/test_telegram_formatter.py` | 盤前抓取與 `[盤前]` 標籤不動 |

---

## Out of Scope

- `daily_pnl_us` cron（Tue–Sat 04:05 台北）與 `us_daily_close_snapshot`
  （Tue–Sat 04:10 台北）為固定台北時間，冬令時對應 15:05 / 15:10 EST
  （收盤前）。本次不改；建議另開 feature 改為 ET-aware cron。
- `_previous_us_trading_date` 的 `hour <= 4` 啟發式不改（本次以半開區間確保相容）。
- 美股假日 / 提前收盤（半日市）判斷。
- `_fetch_premarket_price`、`[盤前]` 標籤、`us_stock_service` cache key。
- `IntervalTrigger` 對齊 :00/:30 或改為 cron。
- 台股 window。
