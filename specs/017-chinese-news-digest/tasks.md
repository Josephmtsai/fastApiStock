# Tasks — 017-chinese-news-digest

依序執行。每個 task 完成後跑 `uv run ruff check . --fix && uv run ruff format .`。

---

## T0 建立 feature branch

- **目標**:自 main 建立並切換至 `feature/017-chinese-news-digest`。
- **指令**:`git checkout main && git pull && git checkout -b feature/017-chinese-news-digest`
- **驗收**:`git branch --show-current` 輸出 `feature/017-chinese-news-digest`。

## T1 news_repo 改抓 Google News RSS

- **目標**:`fetch_news` 改用 Google News RSS zh-TW,簽名不變。
- **涉及檔案**:`src/fastapistock/repositories/news_repo.py`、`pyproject.toml`
- **內容**:
  1. `NewsItem` 增加 `published: str = ''`、`source: str = ''`。
  2. 新增 `_build_query`(TW:`twstock.codes[symbol].name`,
     import 加 `# type: ignore[import-untyped]`,查無 fallback `f'{symbol} 股票'`;
     US:`f'{symbol} 股票'`)。
  3. 移除 yfinance 呼叫;改 `httpx.get('https://news.google.com/rss/search',
     params={'q': query, 'hl': 'zh-TW', 'gl': 'TW', 'ceid': 'TW:zh-Hant'},
     timeout=10, follow_redirects=True)`。
  4. 新增 `_parse_rss`(ElementTree)與 `_clean_title`(截 ` - {source}` 尾綴;
     不匹配保留;截後為空捨棄)。
  5. Cache key 改 `news:v2:{market}:{symbol}:{date}`,payload 含四欄位;
     TTL、隨機延遲、失敗回空 list、空快取 fall-through 全保留。
  6. `pyproject.toml` per-file-ignores:news_repo.py 改為 `["S311", "S314"]`
     並在該行加註理由。
- **驗收**:AC-1.1 ~ AC-1.5;`uv run mypy src/` 無錯;每函式 ≤50 行;無 `Any`。

## T2 news_service 中文關鍵字增補

- **目標**:提升中文標題情緒命中率,不動分類邏輯。
- **涉及檔案**:`src/fastapistock/services/news_service.py`
- **內容**:`_POSITIVE` 增補 `看好/大漲/新高/利多/攀升/走高/調升/優於預期`;
  `_NEGATIVE` 增補 `重挫/利空/走低/大跌/看壞/調降/砍單/不如預期`。
  `classify_sentiment`、`get_sentiment_news`、`SentimentNews` 一律不動。
- **驗收**:既有 test_news_service 測試全綠;spec D-6 詞表完整加入。

## T3 pnl_service 新聞集中至今日焦點區

- **目標**:持股列移除新聞、報告尾端新增焦點區。
- **涉及檔案**:`src/fastapistock/services/pnl_service.py`
- **內容**:
  1. `_build_stock_row` 刪除 L183-192 新聞區塊(保留標題/價格/損益三部分)。
  2. 新增 `_build_news_digest_section(tw_held, us_held) -> str`(演算法見 spec D-5:
     每檔 `get_sentiment_news(symbol, market, max_items=5)` → 濾中性 → 取 2 →
     `🟢/🔴 {symbol} {title}`;單檔例外 log warning 略過;全空回
     `separator + '📰 今日無重點新聞'`)。
  3. `build_pnl_report` 於美股 section 後無條件 append 焦點區
     (tw/us 為 None 時以空 list 傳入)。
  4. import 語句 `from fastapistock.services.news_service import get_sentiment_news`
     保持原樣(測試 patch 目標相依)。
- **驗收**:AC-2.1 ~ AC-2.6;`build_pnl_report` 回傳型別仍 `list[str]`;
  golden sample 結構一致;每函式 ≤50 行。

## T4 測試重寫與新增

- **目標**:依 spec「Affected Tests 盤點」更新三個測試檔,覆蓋率 80%+。
- **涉及檔案**:`tests/test_news_repo.py`(全檔重寫)、
  `tests/test_news_service.py`(新增)、`tests/test_pnl_service.py`(改寫 2 + 新增)
- **內容**:
  - test_news_repo:httpx mock + RSS XML fixture,覆蓋 E-1~E-7、E-10、E-11、E-13,
    含 cache key `news:v2` 斷言、TW query 中文名斷言、US query 斷言。
  - test_news_service:新增中文關鍵字正/負面分類測試。
  - test_pnl_service:改寫 `test_build_pnl_report_shows_news_in_stock_row`
    (→ digest 呈現 + stock row 無 📰)、`test_build_pnl_report_news_exception_shows_no_news`
    (→ 斷言 `今日無重點新聞`);新增 E-8、E-12、每檔上限 2 條、🔴 負面、
    保留字元跳脫測試;其餘既有測試不動並確認全綠。
- **驗收**:`uv run pytest` 全綠;`--cov=src` 總覆蓋率 ≥80%;
  test_scheduler / test_webhook 未修改且全綠。

## T5 全量驗證 + commit + handoff

- **目標**:品質關卡與交付。
- **內容**:
  1. `uv run ruff check . && uv run ruff format --check .`
  2. `uv run mypy src/`
  3. `uv run pytest`(覆蓋率 ≥80%)
  4. `uv run pre-commit run --all-files`
  5. Conventional commit(拆分建議:
     `feat: switch news source to Google News RSS zh-TW`、
     `feat: consolidate news into daily digest section`、
     `test: rewrite news repo tests for RSS source`,或單一
     `feat: chinese news digest for daily pnl report`)
  6. 產出 `specs/017-chinese-news-digest/handoff-dev.json`
     (from: developer, to: qa, status: ready, changed_files 完整列出,
     ac_ref 指向本檔),並告知 orchestrator spawn **codex-reviewer**(非直接 QA)。
- **驗收**:四項檢查全過;commit 訊息符合 Conventional Commits;
  handoff-dev.json 存在且 changed_files 與實際 diff 一致。

---

## AC 對照表

| AC | Task | 驗證方式 |
|----|------|---------|
| AC-1.1 TW query 中文名 + RSS 參數 | T1 / T4 | test_news_repo(query 斷言) |
| AC-1.2 US query `{symbol} 股票` | T1 / T4 | test_news_repo |
| AC-1.3 標題尾綴截除 + source 欄位 | T1 / T4 | test_news_repo |
| AC-1.4 逾時/解析失敗回空 list | T1 / T4 | test_news_repo(E-1~E-3) |
| AC-1.5 快取命中不發 HTTP | T1 / T4 | test_news_repo(E-10) |
| AC-2.1 持股列無新聞行 | T3 / T4 | test_pnl_service(row 無 📰) |
| AC-2.2 焦點區 🟢/🔴 分組格式 | T3 / T4 | test_pnl_service |
| AC-2.3 濾中性後每檔取 2 | T3 / T4 | test_pnl_service |
| AC-2.4 全空顯示今日無重點新聞 | T3 / T4 | test_pnl_service(E-8/E-9) |
| AC-2.5 MarkdownV2 跳脫 | T3 / T4 | test_pnl_service |
| AC-2.6 回傳 list[str] + 4096 分段 | T3 / T4 | 既有測試 + type check |
