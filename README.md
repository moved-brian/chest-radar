# 胸腔科進修雷達 — Chest Radar

自動彙整台灣胸腔暨重症相關學會的課程、研討會與工作坊，整理成一個可篩選的網頁。
架構與 [麻醉科進修雷達](https://github.com/moved-brian/anesth-radar) 相同：Python 爬蟲 → `data/events.json` → 靜態網頁 → GitHub Actions 每 12 小時自動更新 → GitHub Pages。

網址：https://moved-brian.github.io/chest-radar/

## 來源

| 代號 | 學會 | 抓取頁面 | 備註 |
|---|---|---|---|
| TSPCCM | 台灣胸腔暨重症加護醫學會 | `/conference/list?display_date=YYYY-MM` | 主來源，含各醫院討論會與他學會活動；抓上個月～未來 3 個月 |
| 肺癌學會 | 台灣肺癌學會 | `/ehc-tlcs/s/w/edu/courseSearch/courseTypeA` | 只抓第一頁（15 筆，之後的頁面需驗證碼） |
| 結核學會 | 台灣結核暨肺部疾病醫學會 | `/event/` | 活動少 |
| 急救加護 | 台灣急救加護醫學會 | 聯甄課程、非聯甄、ACLS 委員會課程、最新消息 | 同一筆會出現在多個列表，以編號去重 |
| 重症醫學會 | 中華民國重症醫學會 | 其他學會課程、重症課程、聯甄課程 | 爬蟲沿用麻醉雷達 |
| 睡眠學會 | 台灣睡眠醫學學會 | `learn_list.php?sdate=&edate=` | 以日期區間只抓未來 120 天 |

## 每筆資料的欄位（`data/events.json`）

```json
{
  "id": "tspccm-10268",
  "title": "胸腔科特別演講暨個案討論會",
  "date": "2026-10-01", "end_date": "", "time": "17:00 ~ 19:00",
  "source": "TSPCCM", "source_name": "胸腔暨重症加護醫學會",
  "category": "各院討論會", "level": "hospital",
  "organizer": "台大醫學院附設醫院內科部胸腔科",
  "location": "台大醫院14C錫琴講堂", "region": "北區", "online": false,
  "credit": "胸重 B類 2 分",
  "url": "https://tspccm.formosasoft.com/conference/10268",
  "first_seen": "2026-10-24", "scraped_at": "2026-10-24T00:17:00Z"
}
```

- `level`：`society`＝學會／協會／政府機關主辦或跨院公開活動；`hospital`＝單一醫院／科部的例行討論會，網頁預設隱藏（勾「含各院討論會」才顯示）。判斷規則在 `scrapers/base.py` 的 `classify_level()`。
- `region`：由地點、主辦單位文字比對關鍵字推得（北／中／南／東／外島／線上／國外／未標示），規則在 `classify_region()`。TSPCCM 網站的縣市篩選對多數活動沒有資料，所以不用它。
- `first_seen`：第一次被收錄的日期，存在 `data/seen.json`，網頁「新收錄」篩選用。

## 本機執行

```bash
pip install -r requirements.txt
python run.py                      # 全部來源 → data/events.json
python run.py --sources TSPCCM     # 只跑一個來源
python run.py --dry-run            # 只印統計
python run.py --past-days 30       # 保留過去 30 天
```

## 加入新來源

1. 在 `scrapers/` 新增 `xxx.py`，實作 `scrape() -> list[dict]`，用 `base.make_event()` 組裝每筆資料。
2. 在 `scrapers/__init__.py` 的 `ALL_SCRAPERS` 加入。
3. `python run.py --sources XXX --dry-run` 測試。

## 注意事項

- 只抓各學會**公開頁面**的標題與連結，每筆都導回原公告；非官方彙整，實際資訊以主辦單位為準。
- 台灣內科醫學會（tsim.org.tw）的課程頁網址已變更，暫未收錄。
- 台灣肺癌研究學會（taslc.org.tw）與 TSPCCM 是同一套系統，活動也都登錄在 TSPCCM，不另外抓。
