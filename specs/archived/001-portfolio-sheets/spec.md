# Feature Specification: Google Sheets 持倉整合

**Feature Branch**: `001-portfolio-sheets`
**Created**: 2026-04-09
**Status**: Draft
**Context**: 在現有台股 Telegram 推播訊息中，附加用戶的個人持倉資訊（平均成本、未實現損益），協助用戶即時掌握投資績效。

## 概述

使用者將台股持倉資料（代號、持股數、平均成本、未實現損益）維護在一份公開分享的 Google Sheets 中。
系統讀取該試算表，將持倉資訊附加在每次 Telegram 推播訊息的對應股票區塊中。

資料來源採用 Google Sheets CSV 匯出端點（無需 API 金鑰，僅需公開分享連結）。

## User Scenarios & Testing

### User Story 1 - 台股推播附帶持倉資訊 (Priority: P1)

用戶接收定時台股推播時，能在每支持有股票的區塊中看到自己的「平均成本」與「未實現損益」，
不需要再切換至試算表查閱。

**Why this priority**: 核心需求，沒有持倉顯示則此功能無意義。

**Independent Test**: `GET /api/v1/tgMessage/{id}?stock=2330` 觸發推播，Telegram 訊息中出現「持倉」區塊，含平均成本與損益；若 2330 未在試算表中則不顯示持倉區塊。

**Acceptance Scenarios**:

1. **Given** 試算表中 2330 的平均成本為 820，**When** 推播訊息產生，**Then** 訊息中顯示「成本: 820.00」及損益金額
2. **Given** 試算表中不含 0050，**When** 推播 0050，**Then** 訊息正常顯示技術指標，不顯示持倉區塊
3. **Given** 試算表暫時無法存取，**When** 推播觸發，**Then** 技術指標正常顯示，持倉區塊靜默略過（不中斷推播）

---

### User Story 2 - 持倉快取避免重複請求 (Priority: P2)

每次推播觸發不應每次都重新抓取 Google Sheets，應有快取機制，在合理時間內重用資料。

**Why this priority**: Google Sheets HTTP 請求有速率限制風險；持倉資料不需毫秒級更新。

**Independent Test**: 短時間內觸發兩次推播，確認 log 只出現一次「Fetching portfolio」，第二次為快取命中。

**Acceptance Scenarios**:

1. **Given** 快取命中，**When** 推播觸發，**Then** 不發出新的 Google Sheets HTTP 請求
2. **Given** 快取 TTL 到期，**When** 推播觸發，**Then** 重新抓取試算表並更新快取
3. **Given** Redis 不可用，**When** 推播觸發，**Then** 直接抓取試算表（降級，不崩潰）

---

### Edge Cases

- 試算表欄位為空白或格式非數字時（如小計列）：靜默略過，不計入持倉
- 未實現損益欄位含負號或千分位逗號（如 `-75,000`）：正確解析
- 試算表設為非公開：HTTP 錯誤，log warning，持倉資料以空回傳
- 推播多支股票時，只有部分在試算表中：有持倉的顯示，沒有的略過

## Requirements

### Functional Requirements

- **FR-001**: 系統 MUST 透過公開 Google Sheets CSV 匯出 URL 讀取試算表（無需 API 金鑰或 OAuth）
- **FR-002**: 試算表欄位對應 MUST 固定為：A=代號、C=持股數、F=平均成本、I=未實現損益；第一列為標題略過
- **FR-003**: 系統 MUST 在每支台股推播區塊中，附加對應持倉資訊（若試算表含該代號）
- **FR-004**: 持倉區塊 MUST 顯示：平均成本（TWD）、未實現損益（TWD，直接讀 Sheet 計算值）、相對平均成本漲跌幅（%）
- **FR-005**: 試算表資料 MUST 透過 Redis 快取，TTL 由環境變數控制
- **FR-006**: 所有外部連線設定（試算表 ID、分頁 GID、快取 TTL）MUST 從環境變數讀取，不得硬寫入程式碼
- **FR-007**: 試算表讀取失敗時（HTTP 錯誤、逾時）MUST 降級：持倉欄位略過，技術指標仍正常推送
- **FR-008**: 非數字代號（小計列、空白列）MUST 靜默過濾，不影響其他列解析
- **FR-009**: 美股推播不顯示持倉資訊（持倉試算表僅含台股）

### Key Entities

- **PortfolioEntry**: 單一持倉記錄（代號、持股數、平均成本、未實現損益）
- **Portfolio**: 以代號為索引的持倉快照（`代號 → PortfolioEntry`），排程與 API 共用

## Success Criteria

### Measurable Outcomes

- **SC-001**: 試算表中有持倉的台股，推播時 100% 正確顯示持倉區塊
- **SC-002**: 試算表讀取失敗時，推播成功率不受影響（技術指標仍 100% 送出）
- **SC-003**: 快取命中期間，每個 TTL 週期最多發出 1 次 Sheets HTTP 請求
- **SC-004**: 含千分位逗號（`75,000`）與負號（`-12,000`）的損益數字，解析結果 100% 正確

## Assumptions

- Google Sheets 已設為「知道連結的人可以檢視」，不需登入
- 試算表第一列為標題列，從第二列起為持倉資料
- 未實現損益（I 欄）由 Sheet 公式預先計算，系統直接讀取，不自行重算
- 持倉試算表僅含台股（純數字代號），美股不在此範圍
- 快取 TTL 預設 3600 秒（1 小時）

## 不在本次範圍

- 美股持倉顯示
- 試算表寫入（系統為唯讀）
- 自動偵測欄位位置（欄位固定由設定決定）
- 歷史損益追蹤、持倉變化通知
