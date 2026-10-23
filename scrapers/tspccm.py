"""
Scraper: 台灣胸腔暨重症加護醫學會 (TSPCCM) — 活動列表
URL:  https://tspccm.formosasoft.com/conference/list?display_date=YYYY-MM&category=all&city=
      (www.tspccm.org.tw is the same site; the formosasoft host is the canonical one)

The list is server-rendered, one month per request. Each <tr> in #conferenceTable:
  td.col-datetime : one <div> per day → <span class="fs-em">MM-DD</span> (weekday)<br>HH:MM ~ HH:MM
  td[colspan=2]   : <a href="/conference/ID"><span class="text">title</span></a>
  td.col-division : 主辦 / 主持人
  td.col-site     : 地點
  td.col-char7    : 會議積分 (first), 聯絡人 (second)
  td.col-category : 分類 (mostly 未分類)
An empty month renders <tr id="noData">沒有資料</tr>.
"""

import re
import logging
from datetime import datetime

from .base import (fetch_html, soup_of, make_event, classify_level, guess_category,
                   TW_TZ)

log = logging.getLogger(__name__)

BASE_URL    = "https://tspccm.formosasoft.com"
LIST_URL    = f"{BASE_URL}/conference/list"
SOURCE      = "TSPCCM"
SOURCE_NAME = "胸腔暨重症加護醫學會"

_ID_RE     = re.compile(r"/conference/(\d+)")
_DAY_RE    = re.compile(r"(\d{1,2})-(\d{1,2})")
_TIME_RE   = re.compile(r"(\d{1,2}:\d{2})\s*[~～-]\s*(\d{1,2}:\d{2})")
_CREDIT_RE = re.compile(r"([A-Za-z甲乙丙]?類?)\s*(\d+(?:\.\d+)?)\s*分")


def _month_list(months_ahead: int, months_back: int = 1) -> list[str]:
    now = datetime.now(TW_TZ)
    y, m = now.year, now.month
    out = []
    for offset in range(-months_back, months_ahead + 1):
        yy, mm = y, m + offset
        while mm < 1:
            mm += 12; yy -= 1
        while mm > 12:
            mm -= 12; yy += 1
        out.append(f"{yy:04d}-{mm:02d}")
    return out


def _year_for(block_month: int, disp_year: int, disp_month: int) -> int:
    """A list for 2026-11 can show 10-31 (same year) or, for 2026-12, 01-02 (next year)."""
    if disp_month == 12 and block_month == 1:
        return disp_year + 1
    if disp_month == 1 and block_month == 12:
        return disp_year - 1
    return disp_year


def _cell_text(tr, cls: str, nth: int = 0) -> str:
    cells = tr.select(f"td.{cls}")
    if len(cells) <= nth:
        return ""
    return cells[nth].get_text(" ", strip=True)


def parse_month(html: str, display_date: str) -> list[dict]:
    """Parse one month's listing HTML. display_date = 'YYYY-MM'."""
    soup = soup_of(html)
    table = soup.select_one("#conferenceTable") or soup.find("table")
    if table is None:
        log.warning("TSPCCM %s: no table found", display_date)
        return []
    disp_year, disp_month = int(display_date[:4]), int(display_date[5:7])
    events = []

    for tr in table.select("tr"):
        if tr.get("id") == "noData" or tr.find("th"):
            continue
        link = tr.select_one("a[href*='/conference/']")
        if not link:
            continue
        m_id = _ID_RE.search(link.get("href", ""))
        if not m_id:
            continue
        remote_id = m_id.group(1)
        url = f"{BASE_URL}/conference/{remote_id}"

        # Title: the <span class="text"> inside the link (drop the hidden spacer span)
        span = link.select_one("span.text")
        title = (span or link).get_text(" ", strip=True)
        if not title:
            continue

        # Dates: each day block in the datetime cell
        dt_cell = tr.select_one("td.col-datetime")
        dates, times = [], []
        if dt_cell:
            blocks = dt_cell.select("div[style]") or [dt_cell]
            for b in blocks:
                txt = b.get_text(" ", strip=True)
                md = _DAY_RE.search(txt)
                if not md:
                    continue
                mm, dd = int(md.group(1)), int(md.group(2))
                yy = _year_for(mm, disp_year, disp_month)
                try:
                    dates.append(datetime(yy, mm, dd).strftime("%Y-%m-%d"))
                except ValueError:
                    continue
                mt = _TIME_RE.search(txt)
                times.append(f"{mt.group(1)} ~ {mt.group(2)}" if mt else "")
        if not dates:
            continue
        date, end_date = dates[0], (dates[-1] if len(dates) > 1 else "")
        time = times[0] if times else ""

        organizer = _cell_text(tr, "col-division")
        location  = _cell_text(tr, "col-site")
        credit_raw = _cell_text(tr, "col-char7", 0)
        site_cat   = _cell_text(tr, "col-category")

        mc = _CREDIT_RE.search(credit_raw)
        points = float(mc.group(2)) if mc else None
        credit = f"胸重 {credit_raw}" if credit_raw and credit_raw != "申請中" else (
            "胸重 申請中" if credit_raw == "申請中" else "")

        level = classify_level(organizer, title, points)
        if site_cat and site_cat != "未分類":
            category = {"聯甄重症認證課程": "聯甄課程",
                        "胸重主辦研討會": "學會主辦研討會",
                        "一般學術研討會 (B)": "學術研討會"}.get(site_cat, site_cat)
            if level == "hospital" and category == "學術研討會":
                category = "各院討論會"
        else:
            category = guess_category(title, level)

        events.append(make_event(
            id=f"tspccm-{remote_id}", title=title, date=date, end_date=end_date, time=time,
            source=SOURCE, source_name=SOURCE_NAME, category=category, level=level,
            organizer=organizer, location=location, url=url, credit=credit,
        ))
    return events


def scrape(months_ahead: int = 3) -> list[dict]:
    seen, out = set(), []
    for ym in _month_list(months_ahead):
        url = f"{LIST_URL}?display_date={ym}&category=all&city="
        log.info("TSPCCM: fetching %s", url)
        html = fetch_html(url)
        if html is None:
            continue
        evs = parse_month(html, ym)
        log.info("TSPCCM %s: %d rows", ym, len(evs))
        for e in evs:
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            out.append(e)
    log.info("TSPCCM: %d unique events", len(out))
    return out
