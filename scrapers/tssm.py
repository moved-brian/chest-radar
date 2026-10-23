"""
Scraper: 台灣睡眠醫學學會 (TSSM) — 繼續教育學分活動
URL: https://www.tssm.org.tw/learn_list.php?sdate=YYYY-MM-DD&edate=YYYY-MM-DD&page=N

<table class="tablelist">; header row then one <tr> per activity:
  活動日期 | 活動名稱 | 活動時間 | 時數 | 學分 | 主辦單位 | 審核狀態 | 詳細資訊(button + modal)
The modal (div.modal) holds a label/value grid: 活動主題 / 課程屬性(線上課程|實體課程) /
活動日期 / 活動時間 / 時數 / 學分 / 活動地點 / 主辦單位 …
There is no per-activity page, so url points at the filtered list. The modal id
(myModal11197) is the stable record id.
"""

import re
import hashlib
import logging
from datetime import datetime, timedelta

from .base import fetch_html, soup_of, make_event, parse_date, classify_level, guess_category, TW_TZ

log = logging.getLogger(__name__)

BASE_URL    = "https://www.tssm.org.tw"
SOURCE      = "睡眠學會"
SOURCE_NAME = "台灣睡眠醫學學會"

_MODAL_ID_RE = re.compile(r"myModal(\d+)")
_PAGES_RE    = re.compile(r"\d+\s*/\s*(\d+)\s*共\s*(\d+)\s*筆")


def _modal_fields(td) -> dict:
    """Read label/value pairs out of the modal's display:table grid."""
    out = {}
    modal = td.select_one("div.modal")
    if not modal:
        return out
    for row in modal.select("div[style*='table-row']"):
        cells = row.select("div[style*='table-cell']")
        if len(cells) >= 2:
            out[cells[0].get_text(" ", strip=True)] = cells[1].get_text(" ", strip=True)
    return out


def parse_list(html: str, list_url: str) -> list[dict]:
    soup = soup_of(html)
    table = soup.select_one("table.tablelist") or soup.find("table")
    if table is None:
        return []
    events = []
    for tr in table.select("tr"):
        tds = tr.select("td")
        if len(tds) < 7 or tds[0].find("strong"):
            continue
        date = parse_date(tds[0].get_text(" ", strip=True))
        title = tds[1].get_text(" ", strip=True)
        if not date or not title:
            continue
        time      = tds[2].get_text(" ", strip=True)
        credit_n  = tds[4].get_text(" ", strip=True)
        organizer = tds[5].get_text(" ", strip=True)
        status    = tds[6].get_text(" ", strip=True)
        if status and "通過" not in status:
            continue

        fields = _modal_fields(tds[-1])
        location = fields.get("活動地點", "")
        kind     = fields.get("課程屬性", "")
        online   = "線上" in kind
        m_id = _MODAL_ID_RE.search(str(tds[-1]))
        remote_id = m_id.group(1) if m_id else hashlib.md5(f"{title}{date}".encode()).hexdigest()[:10]

        try:
            points = float(credit_n)
        except ValueError:
            points = None
        level = classify_level(organizer, title, points)
        category = guess_category(title, level, default="睡眠積分活動")

        events.append(make_event(
            id=f"tssm-{remote_id}", title=title, date=date, time=time,
            source=SOURCE, source_name=SOURCE_NAME, category=category, level=level,
            organizer=organizer, location=location, url=list_url,
            credit=f"睡眠 {credit_n} 分" if credit_n else "",
            region="線上" if online else None, online=True if online else None,
        ))
    return events


def scrape(days_ahead: int = 120, days_back: int = 7, max_pages: int = 5) -> list[dict]:
    now = datetime.now(TW_TZ)
    sdate = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
    edate = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    seen, out = set(), []
    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/learn_list.php?sdate={sdate}&edate={edate}&page={page}"
        log.info("TSSM: fetching %s", url)
        html = fetch_html(url)
        if html is None:
            break
        evs = parse_list(html, url)
        for e in evs:
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            out.append(e)
        m = _PAGES_RE.search(soup_of(html).get_text(" ", strip=True))
        total_pages = int(m.group(1)) if m else 1
        if page >= total_pages or not evs:
            break
    log.info("TSSM: %d events", len(out))
    return out
