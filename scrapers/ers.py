"""
Scraper: European Respiratory Society (ERS) — upcoming webinars
URL: https://www.ersnet.org/webinars/

The list page is server-rendered; each upcoming webinar is one card:
  <div class="card card__preview …">
    <a class="card-link" href="https://channel.ersnet.org/media-122478-…-10-november-2026">
      <div class="subheading">Webinars</div>
      <div class="h5">From Africa to Europe: …</div>
      <div class="date caption">10 November, 2026</div>
      <div class="venue caption">Online</div>
    </a>
  </div>

The start/end time is only on the detail page ("17:00-18:00 CET"), so every card costs
one extra request. Times are converted to Taiwan time — an evening webinar in Europe is
past midnight here, so the Taiwan date can be one day later than the date ERS prints.
The original European date/time is kept in the event's `note`.
"""

import re
import time
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from .base import fetch_html, soup_of, make_event

log = logging.getLogger(__name__)

LIST_URL    = "https://www.ersnet.org/webinars/"
SOURCE      = "ERS"
SOURCE_NAME = "European Respiratory Society"

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
_DATE_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})")                 # 10 November, 2026
_ID_RE   = re.compile(r"/media-(\d+)")
# 17:00-18:00 CET / 17.00 – 18.30 CEST / 13:00-14:00 UTC
_TIME_RE = re.compile(r"(\d{1,2})[:.](\d{2})\s*[-–—]\s*(\d{1,2})[:.](\d{2})\s*(CES?T|UTC|GMT)\b")


def parse_en_date(text: str) -> Optional[date]:
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    month = _MONTHS.get(m.group(2).lower())
    if not month:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(1)))
    except ValueError:
        return None


def _last_sunday(year: int, month: int) -> date:
    d = date(year, month, 31)                      # only called for March / October
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _utc_offset(d: date, tz: str) -> int:
    """Hours ahead of UTC on that day. ERS writes "CET" all year round, so CET/CEST both
    mean "Central European local time" and summer time is decided by the date."""
    if tz in ("UTC", "GMT"):
        return 0
    return 2 if _last_sunday(d.year, 3) <= d < _last_sunday(d.year, 10) else 1


def to_taiwan(d: date, time_text: str) -> Optional[tuple[str, str, str]]:
    """(taiwan_date, "HH:MM ~ HH:MM" in Taiwan time, original text) or None if no time found."""
    m = _TIME_RE.search(time_text or "")
    if not m:
        return None
    h1, m1, h2, m2 = (int(m.group(i)) for i in range(1, 5))
    if h1 > 23 or h2 > 23 or m1 > 59 or m2 > 59:
        return None
    shift = timedelta(hours=8 - _utc_offset(d, m.group(5)))
    start = datetime(d.year, d.month, d.day, h1, m1) + shift
    end = datetime(d.year, d.month, d.day, h2, m2) + shift
    if end <= start:
        end += timedelta(days=1)
    original = re.sub(r"\s+", " ", m.group(0)).strip()
    return start.strftime("%Y-%m-%d"), f"{start:%H:%M} ~ {end:%H:%M}", original


def parse_list(html: str) -> list[dict]:
    """Cards on the list page → [{remote_id, title, date(date), url}]"""
    rows = []
    for card in soup_of(html).select("div.card.card__preview"):
        a = card.select_one("a.card-link[href]")
        title_el = card.select_one(".h5")
        date_el = card.select_one(".date")
        if not a or not title_el or not date_el:
            continue
        d = parse_en_date(date_el.get_text(" ", strip=True))
        title = title_el.get_text(" ", strip=True)
        url = a["href"].strip()
        if not d or not title or not url.startswith("http"):
            continue
        m = _ID_RE.search(url)
        remote_id = m.group(1) if m else re.sub(r"[^a-z0-9]+", "-", url.lower())[-40:].strip("-")
        rows.append({"remote_id": remote_id, "title": title, "date": d, "url": url})
    return rows


def scrape() -> list[dict]:
    log.info("ERS: fetching %s", LIST_URL)
    html = fetch_html(LIST_URL, timeout=30)
    if html is None:
        return []
    out, seen = [], set()
    for row in parse_list(html):
        if row["remote_id"] in seen:
            continue
        seen.add(row["remote_id"])
        d = row["date"]
        ev_date, ev_time = d.isoformat(), ""
        note = f"歐洲時間 {d.month}/{d.day}，開始時間見原公告"
        detail = fetch_html(row["url"], timeout=30)
        if detail is not None:
            conv = to_taiwan(d, soup_of(detail).get_text(" "))
            if conv:
                ev_date, ev_time, original = conv
                note = f"已換算台灣時間；原訂 {d.month}/{d.day} {original}"
        time.sleep(0.5)
        out.append(make_event(
            id=f"ers-{row['remote_id']}", title=row["title"], date=ev_date, time=ev_time,
            source=SOURCE, source_name=SOURCE_NAME, category="國際 Webinar", level="society",
            organizer=SOURCE_NAME, location="Online", region="線上", online=True,
            url=row["url"], note=note,
        ))
    log.info("ERS: %d events", len(out))
    return out
