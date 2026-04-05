1. 請實作 請實作GET /api/v1/tgMessage/{id}?stock={0}
stock 為台股編號 使用,分隔 如果非數字代號請忽略
2. 修改 /api/v1/stock/{id}
Response 新增ChineseName 股票名稱
{ "status": "success"|"error", "data": [
    {
        Name : //股票代號
        ChineseName: //股票名稱
        price: //現價
        ma20: //月均價
        ma60: //季均價
        LastDayPrice: // 昨天收
        Volume: //成交量
    }
], "message": "" } // error 的話顯示錯誤訊息在message
3. 請依照.env 裡面提供的telegram token and 參數的id 推送到該user 並且列出 以他想看的股票資訊推送 以陣列方式印出多筆資訊
如果沒有stock 或是沒有查到就不要送出
股票名稱: //中文名稱
現價:
月均價:
季均價:
昨天收:
成交量:
