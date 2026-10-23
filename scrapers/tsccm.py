"""
Scraper: 中華民國重症醫學會 (TSCCM)
URL: https://www.tsccm.org.tw/Academic/index_other.asp            其他學會課程（含重症積分）
     https://www.tsccm.org.tw/od/Academic/index.asp?act_kindid=1  重症課程
     https://www.tsccm.org.tw/od/Academic/index.asp?act_kindid=2  聯甄課程

The listing is a run of text blocks:  日期： … 主辦單位： … 課程： … 學分： … 地點： …
(This parser is carried over from anesth-radar, where it has run in production since 2026-06;
 here no keyword filter is applied — every item carries 重症積分 and is in scope.)
"""

import re
import hashlib
import logging
from .base import get_soup, parse_all_dates, make_event, classify_level, guess_category

log = logging.getLogger(__name__)

BASE_URL    = "https://www.tsccm.org.tw"
SOURCE      = "重症醫學會"
SOURCE_NAME = "中華民國重症醫學會"

PAGES = [
    f"{BASE_URL}/Academic/index_other.asp",
    f"{BASE_URL}/od/Academic/index.asp?act_kindid=1",
    f"{BASE_URL}/od/Academic/index.asp?act_kindid=2",
]


def _mk_id(title: str, date: str) -> str:
    key = re.sub(r"\W+", "", title)[:30] + (date or "")
    return "tsccm-" + hashlib.md5(key.encode("utf-8")).hexdigest()[:10]


def _parse_other_page(soup, url: str) -> list[dict]:
    events = []
    if soup is None:
        return events
    content = soup.find("div", id=re.compile("content|main", re.I)) or soup.body
    full_text = content.get_text("\n") if content else soup.get_text("\n")
    blocks = re.split(r"(?=日期：)", full_text)

    for block in blocks:
        if "課程：" not in block:
            continue
        date_m   = re.search(r"日期：\s*(.+?)(?:\n|$)", block)
        course_m = re.search(r"課程：\s*(.+?)(?:\n|$)", block)
        org_m    = re.search(r"主辦單位：\s*(.+?)(?:\n|$)", block)
        place_m  = re.search(r"地點：\s*(.+?)(?:\n|$)", block)
        credit_m = re.search(r"學分：\s*(.+?)(?:\n|$)", block)
        if not course_m:
            continue
        title     = course_m.group(1).strip()
        date_raw  = date_m.group(1).strip() if date_m else ""
        organizer = org_m.group(1).strip() if org_m else ""
        location  = place_m.group(1).strip() if place_m else ""
        credit    = credit_m.group(1).strip() if credit_m else ""

        dates = parse_all_dates(date_raw)
        date = dates[0] if dates else None
        end_date = dates[-1] if len(dates) > 1 and dates[-1] != dates[0] else ""

        level = classify_level(organizer, title)
        category = guess_category(title, level, default="重症積分課程")
        events.append(make_event(
            id=_mk_id(title, date or ""), title=title, date=date, end_date=end_date,
            source=SOURCE, source_name=SOURCE_NAME, category=category, level=level,
            organizer=organizer, location=location, url=url,
            credit=f"重症 {credit}" if credit else "",
        ))
    return events


def _parse_kindid_page(soup, url: str, default_cat: str) -> list[dict]:
    events = []
    if soup is None:
        return events
    for row in soup.select("tr"):
        tds = row.select("td")
        if len(tds) < 3:
            continue
        text = row.get_text(" ", strip=True)
        if "課程" not in text and "活動" not in text:
            continue
        a = row.find("a")
        title = a.get_text(strip=True) if a else tds[-1].get_text(strip=True)
        if not title or len(title) < 4:
            continue
        dates = parse_all_dates(text)
        date = dates[0] if dates else None
        href = a["href"] if a and a.get("href") else url
        full_url = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
        events.append(make_event(
            id=_mk_id(title, date or ""), title=title, date=date,
            source=SOURCE, source_name=SOURCE_NAME, category=default_cat, level="society",
            organizer=SOURCE_NAME, location="", url=full_url, credit="重症",
        ))
    return events


def _get_page_count(soup) -> int:
    if soup is None:
        return 1
    m = re.search(r"頁次[：:]\s*\d+\s*/\s*(\d+)", soup.get_text())
    return int(m.group(1)) if m else 1


def scrape() -> list[dict]:
    all_events = []
    url = PAGES[0]
    log.info("TSCCM: fetching %s", url)
    soup = get_soup(url)
    total = _get_page_count(soup)
    all_events.extend(_parse_other_page(soup, url))
    for pg in range(2, min(total, 4) + 1):
        pg_url = f"{url}?/{pg}.html"
        log.info("TSCCM: fetching page %d", pg)
        all_events.extend(_parse_other_page(get_soup(pg_url), pg_url))

    all_events.extend(_parse_kindid_page(get_soup(PAGES[1]), PAGES[1], "重症課程"))
    all_events.extend(_parse_kindid_page(get_soup(PAGES[2]), PAGES[2], "聯甄課程"))

    seen, unique = set(), []
    for e in all_events:
        key = (e["title"], e["date"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    log.info("TSCCM: %d events after dedup", len(unique))
    return unique
