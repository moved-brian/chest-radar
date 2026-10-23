"""
Chest Radar — shared utilities for all scrapers.

Every scraper exposes  scrape() -> list[dict]  and returns events in this schema:

{
    "id":         "tspccm-10268",      # stable id = source + remote id (dedup / first_seen)
    "title":      str,
    "date":       "YYYY-MM-DD",        # start date ("" if unknown)
    "end_date":   "YYYY-MM-DD" | "",   # last day for multi-day events
    "time":       "17:00 ~ 19:00" | "",
    "source":     "TSPCCM",            # short code (chip label)
    "source_name": "胸腔暨重症加護醫學會",
    "category":   "各院討論會" | "學術研討會" | "年會" | "工作坊" | "聯甄課程" | "ACLS" | ...,
    "level":      "society" | "hospital",   # hospital = 各醫院自己的討論會 (預設隱藏)
    "organizer":  str,
    "location":   str,
    "region":     "北區" | "中區" | "南區" | "東區" | "外島" | "線上" | "國外" | "未標示",
    "online":     bool,
    "credit":     "胸重 B類 2 分" | "",
    "url":        str,
    "scraped_at": ISO datetime (UTC)
}
run.py adds "first_seen" (YYYY-MM-DD, Taiwan time) from data/seen.json.
"""

import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

TW_TZ = timezone(timedelta(hours=8))


def fetch_html(url: str, timeout: int = 20, **kwargs) -> Optional[str]:
    """GET a URL and return decoded HTML text. Returns None on failure.

    - Retries once without certificate verification if the site's TLS chain is broken
      (several Taiwanese society sites have had this problem).
    - Uses the declared charset, but re-decodes with a sniffed charset when the
      declared one produces replacement characters (classic-ASP sites lie about it).
    """
    log = logging.getLogger(__name__)
    try:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, **kwargs)
        except requests.exceptions.SSLError as e:
            log.warning("GET %s: TLS error (%s) — retrying without verification", url, e)
            import urllib3
            urllib3.disable_warnings()
            resp = requests.get(url, headers=HEADERS, timeout=timeout, verify=False, **kwargs)
        resp.raise_for_status()
        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        text = resp.text
        if text.count("�") > 5 and resp.apparent_encoding and resp.apparent_encoding != resp.encoding:
            resp.encoding = resp.apparent_encoding
            text = resp.text
        return text
    except Exception as e:  # noqa: BLE001
        log.error("GET %s failed: %s", url, e)
        return None


def get_soup(url: str, timeout: int = 20, **kwargs) -> Optional[BeautifulSoup]:
    html = fetch_html(url, timeout=timeout, **kwargs)
    return BeautifulSoup(html, "lxml") if html is not None else None


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


# ── Date helpers ────────────────────────────────────────────────────────────

_ISO_RE    = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")           # 2026-06-27
_ISO_SLASH = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")           # 2026/07/17
_ISO_DOT   = re.compile(r"(20\d{2})\.(\d{1,2})\.(\d{1,2})")       # 2026.11.21
_ZH_RE     = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")        # 2026年5月6日
_ROC_RE    = re.compile(r"(?<!\d)(1[01]\d)[./](\d{1,2})[./](\d{1,2})(?!\d)")  # 115.11.21 / 115/11/21


def parse_date(text: str) -> Optional[str]:
    """Return the first date found in text as YYYY-MM-DD (AD), or None."""
    text = (text or "").strip()
    for rx in (_ISO_RE, _ISO_SLASH, _ISO_DOT, _ZH_RE):
        m = rx.search(text)
        if m:
            return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _ROC_RE.search(text)
    if m:
        return _fmt(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3)))
    return None


def parse_all_dates(text: str) -> list[str]:
    """Return every AD date found in text, in order (for date ranges)."""
    text = text or ""
    found = []
    for rx in (_ISO_RE, _ISO_SLASH, _ISO_DOT, _ZH_RE):
        for m in rx.finditer(text):
            found.append((m.start(), _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))))
    for m in _ROC_RE.finditer(text):
        found.append((m.start(), _fmt(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3)))))
    found.sort()
    out = []
    for _, d in found:
        if d and d not in out:
            out.append(d)
    return out


def _fmt(y: int, m: int, d: int) -> Optional[str]:
    try:
        return datetime(y, m, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%d")


# ── Region / online classification ──────────────────────────────────────────

ONLINE_RE = re.compile(
    r"線上|視訊|遠距|直播|webinar|online|zoom|google\s*meet|teams|網路研討|線上影音|虛擬",
    re.I,
)

# Ordered: the first matching pattern wins. Specific names come before generic city words
# so that e.g. 台北慈濟 is 北區 before the bare 慈濟 (=花蓮) rule fires.
_REGION_RULES: list[tuple[re.Pattern, str]] = [
    # 國外
    (re.compile(r"國外|海外|Manila|Philippines|Japan|Tokyo|Osaka|Kyoto|Korea|Seoul|Singapore|Bangkok|Thailand|"
                r"Hong\s*Kong|Vietnam|Malaysia|Kuala|Jakarta|Sydney|Australia|USA|U\.S\.|America|Canada|Europe|"
                r"Vienna|Barcelona|Amsterdam|Berlin|Paris|London|Madrid|Milan|Rome|Copenhagen|Dubai|India|"
                r"Shanghai|Beijing|Macau|澳門|香港|日本|韓國|新加坡|泰國|馬來西亞|越南|菲律賓|美國|加拿大|英國|德國|法國|澳洲|歐洲", re.I), "國外"),
    # 外島
    (re.compile(r"澎湖|金門|馬祖|連江"), "外島"),
    # 慈濟 disambiguation (must precede 東區 generic rule)
    (re.compile(r"台北慈濟|臺北慈濟|新店慈濟"), "北區"),
    (re.compile(r"台中慈濟|臺中慈濟|潭子慈濟"), "中區"),
    (re.compile(r"大林慈濟|斗六慈濟"), "南區"),
    # 東區
    (re.compile(r"花蓮|宜蘭|羅東|台東|臺東|玉里|關山|鳳林|門諾|慈濟|陽明大學附設|陽大附醫|陽明交通大學附設|國軍花蓮|博愛醫院|聖母醫院|馬偕台東|台東馬偕|臺東馬偕"), "東區"),
    # 南區 (specific hospitals / venues first)
    (re.compile(r"雲林|嘉義|台南|臺南|高雄|屏東|斗六|北港|虎尾|麻豆|柳營|永康|新營|佳里|岡山|鳳山|左營|鼓山|前金|苓雅|三民|楠梓|小港|大林|朴子|民雄|"
                r"成大|成功大學|奇美|新樓|郭綜合|高醫|高雄醫學大學|高雄榮|高榮|高雄長庚|義大|阮綜合|聖功|大同醫院|屏東榮|屏基|屏東基督教|輔英|"
                r"嘉基|嘉義基督教|嘉義長庚|聖馬爾定|雲林分院|台大雲林|臺大雲林|安南醫院|市立醫院\(?台南|部立台南|衛福部台南|衛福部臺南|部立嘉義|部立屏東|恆春|"
                r"H2O|水京棧|漢來|福華飯店\s*\(?高雄|萬豪|晶英|長榮桂冠\(?台南|台糖長榮|南科|南區"), "南區"),
    # 中區
    (re.compile(r"台中|臺中|彰化|南投|員林|豐原|大里|太平|沙鹿|清水|梧棲|大甲|烏日|霧峰|埔里|草屯|竹山|鹿港|二林|溪湖|北斗|"
                r"中榮|中國附醫|中國醫藥|中山附醫|中山醫學大學|澄清|光田|童綜合|仁愛醫院|彰基|彰化基督教|秀傳|佑民|部立台中|衛福部台中|衛福部臺中|"
                r"裕元|李方艾美|林酒店|The\s*Lin|日月千禧|長榮桂冠\(?台中|中區"), "中區"),
    # 北區
    (re.compile(r"胸重學會會址|中華路一段74號|"
                r"台北|臺北|北市|新北|基隆|桃園|新竹|竹北|竹東|苗栗|頭份|板橋|林口|淡水|三峽|土城|樹林|新莊|中和|永和|新店|汐止|三重|蘆洲|"
                r"內湖|士林|北投|信義區|松山|大安|中山區|中正區|文山|南港|大同區|萬華|萬芳|中壢|平鎮|龍潭|八德|楊梅|大園|"
                r"榮總|台大醫院|臺大醫院|台大醫學院|臺大醫學院|台大國際會議|三總|三軍總|國泰|新光|馬偕|振興|亞東|雙和|輔大|輔仁|恩主公|耕莘|"
                r"長庚紀念醫院|林口長庚|台北長庚|基隆長庚|和平婦幼|聯合醫院|陽明醫院|忠孝醫院|仁愛院區|中興院區|北醫|臺北醫學大學|台北醫學大學|"
                r"部立桃園|桃園醫院|聖保祿|敏盛|天成|國軍桃園|東元|新竹臺大|新竹台大|台大竹北|馬偕新竹|新竹馬偕|國泰新竹|大千|為恭|部立苗栗|"
                r"張榮發|集思|福華國際文教|公務人力|南港展覽|世貿|國際會議中心|台北國際會議|喜來登\(?新竹|新竹喜來登|寒舍|君悅|晶華|圓山|"
                r"JR東日本|凱達|北區"), "北區"),
]


def classify_region(location: str, organizer: str = "", title: str = "") -> tuple[str, bool]:
    """
    Decide (region, online) from free text. Location is checked first, then organizer,
    then title — a venue name is more reliable than the organizer's home city.
    """
    loc = location or ""
    if ONLINE_RE.search(loc) or (not loc.strip() and ONLINE_RE.search(title or "")):
        return "線上", True
    for text in (loc, organizer or ""):
        if not text:
            continue
        for rx, region in _REGION_RULES:
            if rx.search(text):
                return region, False
    # Title is the weakest signal: country words there are usually topics ("Japan guideline"),
    # so only city names / explicit venues count, and 國外 only for well-known host cities.
    t = title or ""
    if _TITLE_ABROAD_RE.search(t):
        return "國外", False
    for rx, region in _REGION_RULES[2:]:          # skip the 國外 / 外島 rules for titles
        if rx.search(t):
            return region, False
    return "未標示", False


_TITLE_ABROAD_RE = re.compile(
    r"Manila|Tokyo|Osaka|Kyoto|Seoul|Busan|Singapore|Bangkok|Hong\s*Kong|Hanoi|Kuala\s*Lumpur|Jakarta|"
    r"Sydney|Melbourne|Vienna|Barcelona|Amsterdam|Berlin|Paris|London|Madrid|Milan|Rome|Copenhagen|Dubai|"
    r"Shanghai|Beijing|Macau|馬尼拉|東京|首爾|新加坡|曼谷|香港|澳門|上海|北京|維也納|巴塞隆納|阿姆斯特丹", re.I,
)


# ── Level classification (學會級 vs 各院討論會) ──────────────────────────────

SOCIETY_RE = re.compile(
    r"學會|協會|基金會|委員會|公會|聯盟|Society|Association|Foundation|College|Academy|Alliance|"
    r"Consortium|Research\s*Group|Institute|Network|"
    r"衛生局|衛生福利部|疾病管制署|疾管署|健保署|食品藥物|生策|研究中心|教育部|國家|Congress|研究學會",
    re.I,
)
# Organizer is a single hospital / department (the 衛生福利部XX醫院 prefix still means a hospital)
HOSPITAL_ORG_RE = re.compile(r"醫院|分院|醫學中心|總醫院|院區|診所|醫療財團法人|醫療社團法人|睡眠中心|加護中心|部$|科$")
# Titles of a hospital's own routine sessions
HOSPITAL_SESSION_RE = re.compile(
    r"病例討論|個案討論|案例討論|病例併期刊|期刊討論|期刊雜誌|文獻討論|journal|case\s*(conference|discussion)|"
    r"grand\s*round|晨會|多專科|多團隊|MDT|跨團隊|團隊會議|影像診療研討|教學討論|總查房|臨床病理討論|"
    r"死亡及併發症|M&M|MMC|SPC|專題演講暨個案|特別演講暨個案|科內|部內|住院醫師|教學課程|讀書會|簡介\(",
    re.I,
)
# Titles that signal a regional / multi-hospital / open event even when a hospital hosts it
OPEN_EVENT_RE = re.compile(
    r"北區|中區|南區|東區|北部|中部|南部|東部|雲嘉|桃園區|地區|區域|聯合|跨院|跨領域|國際|International|"
    r"全國|Taiwan|年會|半年會|季會|論壇|Forum|Symposium|Conference|研習會|研習營|工作坊|Workshop|認證|訓練課程",
    re.I,
)


def classify_level(organizer: str, title: str = "", credit_points: Optional[float] = None) -> str:
    """
    'society'  — 學會、協會、政府機關主辦，或跨院/區域/公開活動
    'hospital' — 單一醫院/科部自己的例行討論會（預設隱藏）
    """
    org = organizer or ""
    t = title or ""
    pts = credit_points if credit_points is not None else 0

    if HOSPITAL_ORG_RE.search(org) and not re.search(r"學會|協會|公會|聯盟|Society|Association", org, re.I):
        # a hospital hosts it: open only if the title says so, or it is a half-day+ event
        if OPEN_EVENT_RE.search(t):
            return "society"
        if HOSPITAL_SESSION_RE.search(t):
            return "hospital"
        return "society" if pts >= 3 else "hospital"

    if SOCIETY_RE.search(org):
        return "society"

    # organizer unknown or a bare department name ("胸腔內科", "睡眠中心", "")
    if OPEN_EVENT_RE.search(t) and not HOSPITAL_SESSION_RE.search(t):
        return "society"
    if HOSPITAL_SESSION_RE.search(t):
        return "hospital"
    return "society" if pts >= 3 else "hospital"


# ── Category helper ─────────────────────────────────────────────────────────

def guess_category(title: str, level: str, default: str = "學術研討會") -> str:
    t = title or ""
    if re.search(r"聯甄", t):
        return "聯甄課程"
    if re.search(r"年會|會員大會|Annual\s*Meeting|Congress", t, re.I):
        return "年會"
    if re.search(r"工作坊|Workshop|實作|實戰|hands-?on", t, re.I):
        return "工作坊"
    if re.search(r"認證|甄審|考試|模擬考|模擬測驗", t):
        return "認證考試"
    if level == "hospital":
        return "各院討論會"
    return default


def make_event(*, id: str, title: str, date: Optional[str], source: str, source_name: str,
               category: str, level: str, organizer: str = "", location: str = "",
               url: str = "", credit: str = "", time: str = "", end_date: Optional[str] = None,
               region: Optional[str] = None, online: Optional[bool] = None) -> dict:
    title = re.sub(r"\s+", " ", (title or "")).strip()
    organizer = re.sub(r"\s+", " ", (organizer or "")).strip()
    location = re.sub(r"\s+", " ", (location or "")).strip()
    if region is None or online is None:
        r, o = classify_region(location, organizer, title)
        region = region if region is not None else r
        online = online if online is not None else o
    return {
        "id":          id,
        "title":       title,
        "date":        date or "",
        "end_date":    end_date or "",
        "time":        (time or "").strip(),
        "source":      source,
        "source_name": source_name,
        "category":    category,
        "level":       level,
        "organizer":   organizer,
        "location":    location,
        "region":      region,
        "online":      bool(online),
        "credit":      (credit or "").strip(),
        "url":         url,
        "scraped_at":  now_iso(),
    }
