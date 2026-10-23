"""
Scraper: 台灣急救加護醫學會 (SECCM, 重症專科)
Lists (classic ASP, UTF-8, paginated with ?/N.html):
  /news/acls_union.asp      聯甄課程承辦單位   → acls_union_info.asp?/ID.html
  /news/acls_NotUnion.asp   非聯甄課程         → acls_NotUnion_info.asp?/ID.html
  /news/acls_course.asp     ACLS 委員會課程     → acls_course_info.asp?/ID.html
  /orgNews/News_list.asp    最新消息           → News_info.asp?/ID.html

Markup: <div class="list"> <ul> (header, li.th) … then one <ul> per record:
  <li><span>承辦單位：</span>…</li>        (only on acls_union)
  <li><span>日期：</span>2026/09/18<span class="date">～</span>2026/09/20</li>
  <li><a href="acls_union_info.asp?/815.html#here">title</a></li>
  <li><span>地點：</span>…</li>
The numeric ID is shared across lists (815 appears in both 聯甄 and 最新消息), so it is the dedup key.
"""

import re
import logging

from .base import fetch_html, soup_of, make_event, parse_all_dates, classify_region

log = logging.getLogger(__name__)

BASE_URL    = "https://www.seccm.org.tw"
SOURCE      = "急救加護"
SOURCE_NAME = "台灣急救加護醫學會"

LISTS = [
    # (path, default category, pages to fetch)
    ("/news/acls_union.asp",    "聯甄課程",   2),
    ("/news/acls_NotUnion.asp", "非聯甄課程", 1),
    ("/news/acls_course.asp",   "ACLS",       1),
    ("/orgNews/News_list.asp",  "公告",       1),
]

_ID_RE = re.compile(r"_info\.asp\?/?(?:%2F)?(\d+)\.html", re.I)
_NOISE_RE = re.compile(r"衛福部公告|新聞稿|研究成果|投票|名單|須知|甄審原則|公文", re.I)


def _field(ul, label: str) -> str:
    for li in ul.select("li"):
        span = li.find("span")
        if span and label in span.get_text():
            # text after the label span (may include a "～" span for ranges)
            return li.get_text(" ", strip=True).replace(span.get_text(strip=True), "", 1).strip()
    return ""


def parse_list(html: str, path: str, default_category: str) -> list[dict]:
    soup = soup_of(html)
    container = soup.select_one("div.list") or soup
    events = []
    for ul in container.select("ul"):
        a = ul.select_one("a[href*='_info.asp']")
        if not a:
            continue
        href = a.get("href", "")
        m = _ID_RE.search(href)
        if not m:
            continue
        remote_id = m.group(1)
        title = a.get_text(" ", strip=True)
        if not title:
            continue
        folder = path.rsplit("/", 1)[0]
        url = href if href.startswith("http") else f"{BASE_URL}{folder}/{href.lstrip('/')}"
        url = url.split("#")[0]

        date_txt  = _field(ul, "日期")
        location  = _field(ul, "地點")
        organizer = _field(ul, "承辦單位")
        if organizer == title:          # the site sometimes echoes the title into 承辦單位
            organizer = ""

        dates = parse_all_dates(date_txt)
        # Titles often carry the real event date (115.11.21); prefer it when the list
        # date is just the posting date for 公告-type rows.
        title_dates = parse_all_dates(title)
        date = dates[0] if dates else (title_dates[0] if title_dates else None)
        end_date = dates[-1] if len(dates) > 1 and dates[-1] != dates[0] else (
            title_dates[-1] if len(title_dates) > 1 and (dates and title_dates[0] == dates[0]) else "")

        category = default_category
        if _NOISE_RE.search(title) and not re.search(r"開放報名|報名", title):
            category = "公告"            # 公文、名單、新聞稿 — not an event
        elif re.search(r"聯甄", title):
            category = "聯甄課程"
        elif re.search(r"ACLS|高級心臟救命術", title, re.I):
            category = "ACLS"
        elif default_category == "公告" and re.search(r"研討會|課程|Congress|Symposium|工作坊|Workshop|會議", title, re.I):
            category = "學術研討會"

        region, online = classify_region(location, organizer or SOURCE_NAME, title)
        credit = "重症聯甄" if category == "聯甄課程" else ""

        events.append(make_event(
            id=f"seccm-{remote_id}", title=title, date=date, end_date=end_date,
            source=SOURCE, source_name=SOURCE_NAME, category=category, level="society",
            organizer=organizer or SOURCE_NAME, location=location, url=url, credit=credit,
            region=region, online=online,
        ))
    return events


def scrape() -> list[dict]:
    seen, out = set(), []
    for path, cat, pages in LISTS:
        for pg in range(1, pages + 1):
            url = f"{BASE_URL}{path}" + (f"?/{pg}.html" if pg > 1 else "")
            log.info("SECCM: fetching %s", url)
            html = fetch_html(url)
            if html is None:
                continue
            for e in parse_list(html, path, cat):
                if e["id"] in seen:
                    continue
                seen.add(e["id"])
                out.append(e)
    log.info("SECCM: %d unique events", len(out))
    return out
