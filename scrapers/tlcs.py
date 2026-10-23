"""
Scraper: 台灣肺癌學會 (TLCS) — 教育積分認定活動訊息
URL: https://www.tlcs.org.tw/ehc-tlcs/s/w/edu/courseSearch/courseTypeA

Server-rendered <table class="break-table">; the first page (newest 15 courses) needs no
token or captcha. Each data row:
  <tr onclick="location.href='/ehc-tlcs/s/w/edu/scheduleInfo1/schedule/1477'">
    <td data-th="課程期間">2026/11/01 09:10~2026/11/01 16:40</td>
    <td data-th="課程名稱">…</td>
    <td data-th="申請單位">…</td>
    <td data-th="活動地點">…</td>
    <td data-th="認可積分">1</td>
Later pages require a POST with a captcha, so only page 1 is scraped.
"""

import re
import logging

from .base import fetch_html, soup_of, make_event, parse_all_dates, classify_level, guess_category

log = logging.getLogger(__name__)

BASE_URL    = "https://www.tlcs.org.tw"
LIST_URL    = f"{BASE_URL}/ehc-tlcs/s/w/edu/courseSearch/courseTypeA"
SOURCE      = "肺癌學會"
SOURCE_NAME = "台灣肺癌學會"

_HREF_RE = re.compile(r"location\.href\s*=\s*'([^']+)'")
_ID_RE   = re.compile(r"/schedule/(\d+)")
_TIME_RE = re.compile(r"(\d{1,2}:\d{2})\s*~\s*\d{4}/\d{1,2}/\d{1,2}\s*(\d{1,2}:\d{2})")


def _td(tr, label: str) -> str:
    cell = tr.select_one(f"td[data-th='{label}']")
    return cell.get_text(" ", strip=True) if cell else ""


def parse_list(html: str) -> list[dict]:
    soup = soup_of(html)
    events = []
    for tr in soup.select("table tr"):
        onclick = tr.get("onclick", "")
        m = _HREF_RE.search(onclick)
        if not m:
            continue
        path = m.group(1)
        url = path if path.startswith("http") else BASE_URL + path
        m_id = _ID_RE.search(path)
        remote_id = m_id.group(1) if m_id else re.sub(r"\W+", "", path)[-12:]

        period    = _td(tr, "課程期間")
        title     = _td(tr, "課程名稱")
        organizer = _td(tr, "申請單位")
        location  = _td(tr, "活動地點")
        credit_n  = _td(tr, "認可積分")
        if not title:
            continue

        dates = parse_all_dates(period)
        date = dates[0] if dates else None
        end_date = dates[-1] if len(dates) > 1 and dates[-1] != dates[0] else ""
        mt = _TIME_RE.search(period)
        if mt and end_date:
            time = f"{mt.group(1)} 起"          # multi-day: only the first day's start is meaningful
        elif mt:
            time = f"{mt.group(1)} ~ {mt.group(2)}"
        else:
            time = ""

        try:
            points = float(credit_n)
        except ValueError:
            points = None
        level = classify_level(organizer, title, points)
        category = guess_category(title, level, default="肺癌積分活動")

        events.append(make_event(
            id=f"tlcs-{remote_id}", title=title, date=date, end_date=end_date, time=time,
            source=SOURCE, source_name=SOURCE_NAME, category=category, level=level,
            organizer=organizer, location=location, url=url,
            credit=f"肺癌 {credit_n} 分" if credit_n else "",
        ))
    return events


def scrape() -> list[dict]:
    log.info("TLCS: fetching %s", LIST_URL)
    html = fetch_html(LIST_URL)
    if html is None:
        return []
    events = parse_list(html)
    log.info("TLCS: %d events", len(events))
    return events
