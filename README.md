# 高雄菜價快查

手機優先的靜態網站，提供高雄市與鳳山區的蔬果批發行情、豬雞牛羊行情參考，並比較全聯小時達和家樂福線上購物公開商品頁上的蔬果與生肉售價。

## 目前功能

- 查詢農業部近 14 天的高雄市、鳳山區蔬果批發行情，支援品名搜尋、蔬菜／水果篩選，以及兩市場比較。
- 每個批發價格使用元／公斤，並標示市場實際交易日。
- 肉品行情頁列出高雄市、高雄鳳山、高雄岡山、高雄旗山肉品市場最近一次「規格豬」平均成交價、交易頭數、平均重量及交易日期，另列高屏白肉雞門市參考價、全台活牛產地週行情，以及彰化和雲林羊隻拍賣行情。
- 豬價是活豬拍賣成交價；雞價是高屏白肉雞門市參考價；牛價是活牛產地週均價；羊價是拍賣市場活羊成交價。四種行情的交易層級不同，都不代表分切肉或傳統市場攤商零售價。
- GitHub Actions 每 6 小時擷取一次全聯和家樂福官方公開商品頁，整理成靜態價格快照，並重新部署網站。這是官方線上公開價，尚未綁定高雄特定門市。
- GitHub Actions 每 6 小時讀取農業部毛豬、白肉雞行情，以及中央畜產會公開的牛羊行情，整理成肉品快照。毛豬、白肉雞和羊隻依官方每日行情更新；牛隻依官方每週行情更新，排程或來源服務可能延遲。
- 零售頁比價常見蔬菜、水果和按部位分類的豬牛雞羊鴨生肉；這是精選品項快照，並非通路全部商品。相同食材會合併顯示，避免商品規格太多造成干擾；有其他規格時可展開查看。能從品名辨識重量時會附約每公斤價格並優先排序；加工食品不列入比價。
- 全聯、家樂福沒有在這個版本使用公開即時價格 API；擷取程式讀取官方公開商品頁。頁面結構變更時，擷取規則可能需要更新。
- 高雄市公有零售市場行情的舊資料集已下架，傳統市場攤商零售價目前沒有接入可用的即時來源。

## 行情資料與限制

- 農業部資料：[農產品交易行情](https://data.gov.tw/dataset/8066)；資料集標示每日更新，提供交易日期、作物、市場、平均價和交易量。
- 農業部資料：[毛豬交易行情](https://data.gov.tw/dataset/7296)；資料集提供市場交易日期、成交頭數、平均重量及價格，按日更新。
- 農業部資料：[家禽交易行情（白肉雞／雞蛋）](https://data.gov.tw/dataset/7536)；包括白肉雞高屏門市價格，單位為元／台斤，按日更新。
- 中央畜產會[畜產行情資訊網](https://ppg.naif.org.tw/naif/marketinformation/reference/reference.aspx)提供[活牛產地每週行情](https://www.naif.org.tw/infoBeefCattleDaily.aspx?frontTitleMenuID=37)與[羊隻拍賣市場行情](https://www.naif.org.tw/infoSheepDaily.aspx?fontCss=3&frontMenuID=159&frontTitleMenuID=37)；牛價按週、羊價按市場拍賣日公布，均為活體交易參考價。
- 農業部另有[畜產都市零售價格](https://data.gov.tw/dataset/37952)，但該資料集按年更新且沒有縣市或市場欄位，不適合併入高雄每日市場行情。
- 全聯：讀取[全聯小時達](https://shop.pxgo.com.tw/hourArrive/)公開搜尋結果。
- 家樂福：讀取[家樂福線上購物](https://online.carrefour.com.tw/zh/)蔬果、菇類及肉品搜尋結果。
- 超市資料是線上商品頁的公開售價快照，不代表高雄每一家門市的 POS 貨架價。配送／取貨地區、庫存和促銷可能改變售價，請以商家結帳頁為準。
- 零售快照每 6 小時更新，GitHub 排程可能延後；不是秒級即時報價。頁面會顯示擷取時間。
- 不同通路的商品規格可能不同；只有在品名可辨識重量時才顯示每公斤換算價。

## 部署到 GitHub Pages

1. 在 GitHub 建立一個新的 repository。
2. 把此資料夾**裡面的所有檔案**上傳到 repository 根目錄，包含隱藏的 `.github/workflows/deploy.yml`。
3. 將預設分支命名為 `main`，並推送變更。
4. 到 repository 的 **Settings → Pages**，確認 **Build and deployment → Source** 設為 **GitHub Actions**。
5. 在 **Actions** 頁籤等候 `Deploy to GitHub Pages` 完成。成功後從 workflow 的部署結果開啟網站。

每次推送到 `main` 都會重新擷取零售頁面價格並部署。排程每 6 小時執行一次；要手動更新時，可到 **Actions → Deploy to GitHub Pages → Run workflow**。

## 專案結構

- `index.html`、`styles.css`、`app.js`：網站介面與瀏覽器資料呈現。
- `scripts/fetch_retail_prices.py`：以 Python 標準函式庫擷取公開商品頁和規格，不需要 API 金鑰或其他套件。
- `scripts/fetch_livestock_prices.py`：讀取農業部毛豬、白肉雞行情與中央畜產會牛羊行情，整理最新行情快照。
- `data/retail-prices.json`：零售價格快照；GitHub Actions 每次執行時會重新產生。
- `data/livestock-prices.json`：高雄肉品市場毛豬拍賣、白肉雞高屏門市價、全台活牛產地週行情與彰化／雲林羊隻拍賣行情快照；GitHub Actions 每次執行時會重新產生。
- `.github/workflows/deploy.yml`：推送、手動執行或排程觸發的 Pages 部署工作流程。

本機預覽可在專案目錄執行 `python -m http.server 8000`，再用瀏覽器開啟 `http://localhost:8000`。本機若要更新零售快照，可先執行 `python scripts/fetch_retail_prices.py`。
