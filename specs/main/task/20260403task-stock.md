1. 請實作 串接  yfinance 並且將依賴包安裝到.venv

2. 請實作GET /api/v1/stock/{id}  {Id}為台股代碼 ex 0050,2330,2317 使用逗號串接

Response 為
{ "status": "success"|"error", "data": [
    {
        Name : //股票代號
        price: //現價
        ma20: //月均價
        ma60: //季均價
        LastDayPrice: // 昨天收
        Volume: //成交量
    }
], "message": "" } // error 的話顯示錯誤訊息在message


3. 資料邏輯串接請依照constitution or Plan放在對應的folder
