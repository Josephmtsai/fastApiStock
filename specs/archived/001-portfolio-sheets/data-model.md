# Data Model: Google Sheets 持倉整合

**Branch**: `001-portfolio-sheets` | **Date**: 2026-04-09

## 1. PortfolioEntry（持倉記錄）

單一股票的持倉快照，從 Google Sheets 讀取，不持久化（僅存於 Redis 快取）。

```python
@dataclass(frozen=True)
class PortfolioEntry:
    """A single portfolio position read from Google Sheets.

    Attributes:
        symbol: Taiwan stock code (e.g. '2330').
        shares: Number of shares held (unit matches the sheet).
        avg_cost: Average cost per share in TWD.
        unrealized_pnl: Unrealised P&L in TWD (pre-calculated in sheet).
    """
    symbol: str
    shares: int
    avg_cost: float
    unrealized_pnl: float
```

**來源**: `src/fastapistock/repositories/portfolio_repo.py`

**驗證規則**:
- `symbol`：非空且為純數字（台股代號），非數字字串靜默略過
- `shares`：可為 0（持倉已清空但列尚未移除）
- `avg_cost`：float，含千分位逗號的字串統一由 `_parse_number()` 解析
- `unrealized_pnl`：float，可為負，含負號與千分位逗號

---

## 2. RichStockData 擴充欄位

現有 `RichStockData`（`src/fastapistock/schemas/stock.py`）新增三個可選欄位。
原有欄位不動，向後相容。

```python
class RichStockData(BaseModel):
    # ... 現有欄位（不變）...

    # 新增：持倉資料（由 portfolio_repo 注入，無持倉時為 None）
    avg_cost: float | None = None
    unrealized_pnl: float | None = None
    shares: int | None = None
```

**注入時機**: `stock_service.get_rich_tw_stocks()` 呼叫 `_merge_portfolio()` 後填入
**美股**: `us_stock_service.get_us_stocks()` 不呼叫 merge，三欄保持 `None`

---

## 3. Redis 快取格式

**Key**: `portfolio:tw`
**TTL**: `PORTFOLIO_CACHE_TTL` 秒（env var，預設 3600）
**Value** (JSON):

```json
{
  "2330": {"shares": 1000, "avg_cost": 820.0, "unrealized_pnl": 75000.0},
  "0050": {"shares": 500,  "avg_cost": 185.0, "unrealized_pnl": 5250.0}
}
```

**注意**: Redis 值的型別為 `dict[str, object]`（`redis_cache.get()` 回傳型別），
讀取時需 `cast(dict[str, object], raw)` 後再取個別欄位。

---

## 4. 欄位索引常數（模組私有）

定義於 `src/fastapistock/repositories/portfolio_repo.py`：

```python
# Column indices (0-based) — maps to Google Sheets column letters:
# A=代號, B=股票名稱(skip), C=持股數, D-E=skip, F=平均成本, G-H=skip, I=未實現損益
_COL_SYMBOL         = 0   # A
_COL_SHARES         = 2   # C
_COL_AVG_COST       = 5   # F
_COL_UNREALIZED_PNL = 8   # I
```

---

## 5. 環境變數

| 變數名 | 型別 | 預設值 | 說明 |
|--------|------|--------|------|
| `GOOGLE_SHEETS_ID` | str | `''` | Google Sheets 試算表 ID（URL 中的長字串） |
| `GOOGLE_SHEETS_PORTFOLIO_GID` | str | `''` | 持倉分頁的 GID（URL 中 `gid=` 後的數字） |
| `PORTFOLIO_CACHE_TTL` | int | `3600` | Redis 快取存活秒數 |

若 `GOOGLE_SHEETS_ID` 或 `GOOGLE_SHEETS_PORTFOLIO_GID` 為空，`fetch_portfolio()` 直接 log warning 並回傳空 dict，不影響推播。
