"""
Scraper: 台灣結核暨肺部疾病醫學會 (TSTLD) — 活動列表
URL: https://www.tstld.org/event/          (all categories)
     https://www.tstld.org/event/4         (學術研討會)
     https://www.tstld.org/event/5         (結核病防治教育訓練)

Each event block:
  <div class="content">
    <div class="top-content"><div class="news-title"><a href="https://www.tstld.org/event_detail/35">title</a></div>
                             <p class="des">…</p></div>
    <div class="info-list"><div class="info"><p class="data"> 活動日期:2026/11/11 ~ 2026/11/11 </p></div>
                           <div class="info"><p class="data">學術研討會</p></div></div>
  </div>
"""

import re
import logging

from .base import fetch_html, soup_of, make_event, parse_all_dates

log = logging.getLogger(__name__)

BASE_URL    = "https://www.tstld.org"
LIST_URLS   = [f"{BASE_URL}/event/", f"{BASE_URL}/event/4", f"{BASE_URL}/event/5"]
SOURCE      = "結核學會"
SOURCE_NAME = "台灣結核暨肺部疾病醫學會"

_ID_RE = re.compile(r"/event_detail/(\d+)")


def parse_list(html: str) -> list[dict]:
    soup = soup_of(html)
    events = []
    for a in soup.select("a[href*='/event_detail/']"):
        m = _ID_RE.search(a.get("href", ""))
        title = a.get_text(" ", strip=True)
        if not m or not title:
            continue
        remote_id = m.group(1)
        url = f"{BASE_URL}/event_detail/{remote_id}"

        block = a.find_parent("div", class_="content") or a.find_parent("div") or a
        datas = [p.get_text(" ", strip=True) for p in block.select("p.data")]
        date_txt = next((d for d in datas if "活動日期" in d), "")
        site_cat = next((d for d in datas if d and "活動日期" not in d), "")
        des = block.select_one("p.des")
        des_txt = des.get_text(" ", strip=True) if des else ""
        location = ""
        ml = re.search(r"地點[:：]\s*(.+)", des_txt)
        if ml:
            location = ml.group(1).strip()

        dates = parse_all_dates(date_txt)
        date = dates[0] if dates else None
        end_date = dates[-1] if len(dates) > 1 and dates[-1] != dates[0] else ""

        category = site_cat or "學術研討會"
        if "甄審" in category or "考試" in category:
            category = "認證考試"
        elif "教育訓練" in category:
            category = "教育訓練"

        events.append(make_event(
            id=f"tstld-{remote_id}", title=title, date=date, end_date=end_date,
            source=SOURCE, source_name=SOURCE_NAME, category=category, level="society",
            organizer=SOURCE_NAME, location=location, url=url,
        ))
    return events


def scrape() -> list[dict]:
    seen, out = set(), []
    for url in LIST_URLS:
        log.info("TSTLD: fetching %s", url)
        html = fetch_html(url)
        if html is None:
            continue
        for e in parse_list(html):
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            out.append(e)
    log.info("TSTLD: %d events", len(out))
    return out
