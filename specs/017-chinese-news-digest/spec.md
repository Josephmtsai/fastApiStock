# Spec 017 — 每日損益報告新聞中文化與集中呈現 (chinese-news-digest)

## Overview

將每日損益報告的新聞源從 yfinance 英文新聞換成 Google News RSS 中文版(zh-TW),
並將新聞從每檔持股列中移除、集中到報告尾端「📰 今日焦點」區,只顯示有情緒訊號
(正面/負面)的新聞。

## User Stories

### US-1 中文新聞源
As a 投資人, I want 損益報告的新聞標題以繁體中文呈現,
so that 我不需要翻譯就能快速掌握持股相關消息。

- **AC-1.1** Given 快取未命中且 Google News RSS 正常回應,
  When `fetch_news('2330', 'TW')` 被呼叫,
  Then 以 `https://news.google.com/rss/search?q=台積電&hl=zh-TW&gl=TW&ceid=TW:zh-Hant`
  抓取(query 為 URL-encoded 中文公司名),回傳的 `NewsItem.title` 為中文標題。
- **AC-1.2** Given 美股 symbol `AAPL`,
  When `fetch_news('AAPL', 'US')` 被呼叫,
  Then query 為 `AAPL 股票`(URL-encoded),其餘 RSS 參數同上。
- **AC-1.3** Given RSS item 標題為 `台積電法說會釋利多 - 經濟日報` 且
  `<source>` 元素文字為 `經濟日報`,
  When 解析該 item,
  Then `NewsItem.title == '台積電法說會釋利多'`(尾綴 ` - {source}` 被截除),
  `NewsItem.source == '經濟日報'`。
- **AC-1.4** Given HTTP 逾時、非 2xx、或 XML 解析失敗,
  When `fetch_news` 被呼叫,
  Then 回傳空 list 並記 warning log,不拋例外(與既有行為一致)。
- **AC-1.5** Given 快取命中且 items 非空,
  When `fetch_news` 被呼叫,
  Then 不發出任何 HTTP 請求,直接回傳快取內容。

### US-2 新聞集中呈現
As a 投資人, I want 新聞集中在報告尾端且只看有訊號的新聞,
so that 損益區塊乾淨、重點新聞一眼可見。

- **AC-2.1** Given 任意持股,
  When `build_pnl_report` 產出報告,
  Then 每檔持股列只含:標題行、現價/漲跌行、持倉損益行,**不含** `📰` 行。
- **AC-2.2** Given 2330 有 1 條正面新聞、AAPL 有 1 條負面新聞,
  When 產出報告,
  Then 報告尾端出現「📰 *今日焦點*」區,含
  `🟢 2330 {標題}` 與 `🔴 AAPL {標題}`(先台股後美股,依持股順序)。
- **AC-2.3** Given 某檔股票取得 5 條新聞,其中第 1、2 條為中性、第 3、4、5 條為正面,
  When 產出焦點區,
  Then 該檔顯示第 3、4 條(過濾中性後取前 2 條,每檔上限 2 條)。
- **AC-2.4** Given 所有持股的新聞皆為中性、或皆無新聞、或全部抓取失敗,
  When 產出報告,
  Then 焦點區僅顯示一行 `📰 今日無重點新聞`。
- **AC-2.5** Given 新聞標題含 MarkdownV2 保留字元(如 `.`、`-`、`(`),
  When 產出報告,
  Then 標題經 `_esc()` 跳脫,Telegram 不會回 parse error。
- **AC-2.6** Given 報告全文超過 4096 字元,
  When 產出報告,
  Then 沿用既有 `_split_message` 分段,`build_pnl_report` 仍回傳 `list[str]`。

## Modules

| Module | 職責 | 涉及檔案 |
|--------|------|---------|
| news_repo | Google News RSS 抓取、RSS 解析、標題清理、Redis 快取 | `src/fastapistock/repositories/news_repo.py` |
| news_service | 情緒分類(僅增補中文關鍵字,邏輯不動) | `src/fastapistock/services/news_service.py` |
| pnl_service | 移除持股列新聞、新增「今日焦點」尾端區 | `src/fastapistock/services/pnl_service.py` |
| pyproject | per-file-ignores 增加 S314 | `pyproject.toml` |
| tests | 重寫/更新三個測試檔 | `tests/test_news_repo.py`, `tests/test_news_service.py`, `tests/test_pnl_service.py` |

## Design Decisions(已定案,developer 不得更改)

### D-1 Query 建構規則
- **TW**:優先用 `twstock.codes[symbol].name` 取得中文公司名(本地映射、零網路呼叫;
  twstock 已是宣告依賴)。查無時 fallback `f'{symbol} 股票'`。
  匯入需 `# type: ignore[import-untyped]`(比照 `scripts/backfill_history.py` L85)。
- **US**:一律 `f'{symbol} 股票'`(如 `AAPL 股票`)。理由:美股 ticker 在中文財經媒體
  普遍使用,精準度高;`display_name` 是英文全名(如 `Apple Inc.`),在 zh-TW 語系
  搜尋命中率反而較差。
- **簽名不變**:query 於 `fetch_news` 內部建構,`fetch_news(symbol, market)` 對外
  簽名維持不變,呼叫端(news_service)零改動。
- query 必須經 `urllib.parse.quote`(或 httpx `params=`)編碼。

### D-2 RSS 抓取與解析
- 使用 `httpx.get(url, params=..., timeout=10, follow_redirects=True)`(比照
  `portfolio_repo.py` L95 慣例)。
- 解析用 stdlib `xml.etree.ElementTree.fromstring`,**不新增第三方依賴**。
  Ruff S314 需在 `pyproject.toml` per-file-ignores 對 news_repo.py 加入
  (該檔已有 `["S311"]` → 改為 `["S311", "S314"]`),註釋理由:來源為 Google News
  HTTPS 端點,ElementTree 預設不解析外部實體,DTD 炸彈風險由上游端點信任邊界承擔。
- item 欄位對應:`<title>` → title、`<link>` → url、`<pubDate>` → published
  (原字串,不解析)、`<source>` → source。
- **標題尾綴清理**:若 title 以 ` - {source文字}` 結尾則截除該尾綴;
  `<source>` 缺失或不匹配時保留原標題。清理後空字串的 item 捨棄。
- 保留:隨機延遲 `time.sleep(random.uniform(0.5, 1.5))`(快取未命中時,兩市場皆延遲)、
  `_MAX_FETCH = 5`、失敗回空 list、空 items 快取命中時 fall-through 重抓。

### D-3 快取
- Key 改版:`news:v2:{market}:{symbol}:{date}`(加 `v2` 前綴,部署後自動繞過
  舊 yfinance 英文快取,4h TTL 內不會混出英文新聞)。TTL 維持 `4 * 60 * 60`。
- 快取 payload:`{'items': [{'title', 'url', 'published', 'source'}, ...]}`。

### D-4 NewsItem 擴充(向後相容)
frozen dataclass 新增 default 欄位,既有 `NewsItem(title=..., url=...)` 建構不受影響。

### D-5 焦點區演算法(pnl_service)
1. `_build_stock_row` 刪除 L183-192 新聞 try/except 區塊。
2. 新增 `_build_news_digest_section(tw_held, us_held) -> str`:
   - 依序走訪 tw_held、us_held(持股順序)。
   - 每檔呼叫 `get_sentiment_news(symbol, market, max_items=5)`,
     過濾 `sentiment != '中性'`,取前 2 條。
   - 每條格式:`{'🟢' if 正面 else '🔴'} {_esc(symbol)} {_esc(title)}`。
   - 單檔例外(如 get_sentiment_news 拋錯)→ log warning、視為該檔無新聞,
     不影響其他檔。
   - 有訊號新聞:回傳 `{separator}\n📰 *今日焦點*\n\n{lines joined by \n}`;
     全空:回傳 `{separator}\n📰 今日無重點新聞`。
     (separator 為既有 `\-` x14 樣式)
3. `build_pnl_report` 在美股明細 section 之後 append 焦點區(無條件,包含
   tw/us 皆讀取失敗的情況——此時 held 為空、顯示無重點新聞)。
4. `get_sentiment_news` 的 import 位置與名稱不變
   (`from fastapistock.services.news_service import get_sentiment_news`),
   確保既有測試 patch 目標 `fastapistock.services.pnl_service.get_sentiment_news`
   繼續有效。
5. 每個函式 ≤50 行;必要時將單檔新聞行組裝拆成
   `_collect_stock_news_lines(stock, market) -> list[str]` helper。

### D-6 情緒關鍵字小幅增補(不重寫邏輯)
- `_POSITIVE` 增補:`'看好'`, `'大漲'`, `'新高'`, `'利多'`, `'攀升'`, `'走高'`,
  `'調升'`, `'優於預期'`
- `_NEGATIVE` 增補:`'重挫'`, `'利空'`, `'走低'`, `'大跌'`, `'看壞'`, `'調降'`,
  `'砍單'`, `'不如預期'`
- `classify_sentiment` 與 `get_sentiment_news` 邏輯、簽名皆不動。

## Data Contracts

```python
# src/fastapistock/repositories/news_repo.py
@dataclass(frozen=True)
class NewsItem:
    """Single news headline for a stock."""
    title: str
    url: str
    published: str = ''   # 原始 RFC-822 pubDate 字串,不解析
    source: str = ''      # 媒體名(<source> 元素文字)

def fetch_news(symbol: str, market: Literal['TW', 'US']) -> list[NewsItem]: ...
# 簽名不變;內部新增私有 helper:
def _build_query(symbol: str, market: Literal['TW', 'US']) -> str: ...
def _parse_rss(xml_text: str) -> list[NewsItem]: ...
def _clean_title(title: str, source: str) -> str: ...

# src/fastapistock/services/news_service.py — 簽名皆不變
Sentiment = Literal['正面', '中性', '負面']
class SentimentNews: title: str; sentiment: Sentiment
def classify_sentiment(title: str) -> Sentiment: ...
def get_sentiment_news(symbol, market, max_items: int = 2) -> list[SentimentNews]: ...

# src/fastapistock/services/pnl_service.py
def build_pnl_report(now: datetime) -> list[str]: ...   # 對外介面不變
def _build_news_digest_section(
    tw_held: list[RichStockData],
    us_held: list[RichStockData],
) -> str: ...
```

Redis payload(key `news:v2:{market}:{symbol}:{YYYY-MM-DD}`,TTL 14400s):

```json
{
  "items": [
    {
      "title": "台積電法說會釋利多",
      "url": "https://news.google.com/rss/articles/...",
      "published": "Fri, 04 Jul 2026 08:30:00 GMT",
      "source": "經濟日報"
    }
  ]
}
```

## API Design

無新增/變更 HTTP 路由。`POST /webhook`(pnl 推送)與 scheduler job 僅透過
`build_pnl_report(now) -> list[str]` 消費,介面不變。

## Golden Sample(新報告完整範例,Telegram 渲染後樣貌)

```
📊 每日損益報告 2026-07-05

💰 帳戶總覽
🇹🇼 台股今日：+NT$15,000 ｜ 持倉：+NT$45,000
🇺🇸 美股今日：-US$32.00 (≈NT$-1,040) ｜ 持倉：+NT$120,000

--------------
🇹🇼 台股明細

2330 台積電
現價 1085.0 | 今日 +15.0 (+1.4%)
持倉損益 +NT$45,000

--------------
🇺🇸 美股明細

AAPL Apple Inc.
現價 212.5 | 今日 -3.2 (-1.48%)
持倉損益 -US$800.00

--------------
📰 今日焦點

🟢 2330 台積電先進製程需求強勁 法人看好下半年
🔴 AAPL 蘋果中國市場銷售下滑 分析師調降目標價
```

全部中性/無新聞時,最後一段改為:

```
--------------
📰 今日無重點新聞
```

(實際輸出為 MarkdownV2:粗體 `*...*`、所有保留字元經 `_esc()` 反斜線跳脫,
分隔線為 `\-` x14;超過 4096 字元由 `_split_message` 分段。)

## Edge Cases

| # | 情境 | 行為 |
|---|------|------|
| E-1 | RSS HTTP 逾時 / 連線錯誤 | log warning、回空 list、該檔視為無新聞 |
| E-2 | RSS 回 4xx/5xx | 同 E-1(以 `raise_for_status` 或狀態碼判斷) |
| E-3 | XML 解析失敗(`ParseError`) | 同 E-1 |
| E-4 | RSS 回 0 個 item | 回空 list;快取存空 items(讀取時 fall-through 重抓,沿用既有行為) |
| E-5 | 標題含 MarkdownV2 保留字元 | 焦點區輸出前經 `_esc()` 跳脫 |
| E-6 | 標題截除尾綴後為空字串 | 捨棄該 item |
| E-7 | `<source>` 缺失或與尾綴不匹配 | 保留原標題不截 |
| E-8 | 全部持股新聞皆中性 | 焦點區顯示 `📰 今日無重點新聞` |
| E-9 | 無任何持股(tw/us held 皆空)或行情讀取失敗 | 焦點區顯示 `📰 今日無重點新聞`,報告其餘部分不變 |
| E-10 | 快取命中(items 非空) | 不發 HTTP、不延遲,直接回傳 |
| E-11 | 快取未命中 | 隨機延遲 0.5–1.5s 後抓取,結果寫入快取 |
| E-12 | 單檔 `get_sentiment_news` 拋例外 | 該檔略過並 log warning,其他檔正常呈現 |
| E-13 | `twstock.codes` 查無該台股代碼 | query fallback `f'{symbol} 股票'` |
| E-14 | 焦點區使報告超過 4096 字元 | 既有 `_split_message` 於換行處分段 |

## Affected Tests 盤點

| 檔案 | 影響 | 處置 |
|------|------|------|
| `tests/test_news_repo.py` | **全部 6 個測試失效**(mock 目標 `yfinance.Ticker` 不再存在於流程) | 全檔重寫:httpx mock + RSS XML fixture。必含:快取命中不發 HTTP、快取未命中發 HTTP 並寫快取、HTTP 逾時回空、XML 壞損回空、標題尾綴截除、TW query 用中文名(mock `twstock.codes`)、US query 為 `{symbol} 股票`、cache key 為 `news:v2:...` 含日期、空 items 快取 fall-through |
| `tests/test_news_service.py` | 不失效(`NewsItem(title, url)` 建構因 default 欄位仍合法;patch 目標 `news_service.fetch_news` 不變) | 保留全部;新增中文關鍵字分類測試(如 `'看好'` → 正面、`'重挫'` → 負面) |
| `tests/test_pnl_service.py` L178 `test_build_pnl_report_shows_news_in_stock_row` | **失效**(斷言 `'正面'` 標籤,新格式無此字樣;新聞不再在 stock row) | 改寫為 digest 測試:斷言 `今日焦點`、`🟢`、symbol 出現於焦點區、股票明細列不含 `📰` |
| `tests/test_pnl_service.py` L227 `test_build_pnl_report_news_exception_shows_no_news` | **失效**(斷言 `'暫無新聞'`,該字樣移除) | 改斷言 `今日無重點新聞` |
| `tests/test_pnl_service.py` 其餘 13 處 `patch(...pnl_service.get_sentiment_news, return_value=[])` | patch 目標不變、回空 → 焦點區顯示無重點新聞,原斷言不受影響 | 保留不動;執行驗證 |
| `tests/test_pnl_service.py` 新增 | — | 全中性→無重點新聞、每檔上限 2 條(5 條訊號只取 2)、負面顯示 🔴、單檔例外不影響他檔、標題保留字元跳脫 |
| `tests/test_scheduler.py` / `tests/test_webhook.py` | 不受影響(patch 整個 `build_pnl_report`) | 不動 |

## Out of Scope

- **LLM 新聞摘要 / 翻譯**(明確排除;純換源,不做生成式摘要)
- 情緒分類邏輯重寫(僅關鍵字增補)
- 新聞 URL 呈現於報告中(維持只顯示標題)
- rich 推播(`telegram_service.py`)任何改動
- `_split_message` / `_esc` 改動
- 價格警示、新聞推播頻率調整
- `published` 時間過濾(「今日」語意由 date-scoped cache key 近似,不解析 pubDate)
