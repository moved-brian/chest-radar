#!/usr/bin/env python3
"""
Chest Radar — main runner
    python run.py                         # scrape every source → data/events.json
    python run.py --sources TSPCCM 肺癌學會
    python run.py --dry-run               # print counts only
    python run.py --past-days 30          # keep events up to 30 days in the past

data/seen.json remembers when each event id was first collected, so the site can
offer a 「新收錄」 filter (自上次造訪 / 近 3 天 / 近 7 天).
"""

import argparse
import json
import logging
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scrapers import ALL_SCRAPERS                      # noqa: E402
from scrapers.base import today_tw                     # noqa: E402

log = logging.getLogger("run")
DATA_DIR    = Path(__file__).parent / "data"
OUTPUT_FILE = DATA_DIR / "events.json"
SEEN_FILE   = DATA_DIR / "seen.json"
SEEN_KEEP_DAYS = 120


def norm_title(t: str) -> str:
    t = re.sub(r"[\s【】\[\]（）()「」『』:：,，.。、/／_\-–—~～|｜*＊!！?？'\"“”]", "", t or "")
    return t.lower()[:24]


def dedup(events: list[dict]) -> list[dict]:
    """Drop exact id duplicates, then near-duplicates (same normalised title + start date)."""
    seen_id, seen_key, unique = set(), set(), []
    for e in events:
        if e["id"] in seen_id:
            continue
        key = (norm_title(e["title"]), e["date"])
        if key[0] and key in seen_key:
            continue
        seen_id.add(e["id"])
        seen_key.add(key)
        unique.append(e)
    return unique


def filter_window(events: list[dict], past_days: int) -> list[dict]:
    today = date.fromisoformat(today_tw())
    cutoff = today - timedelta(days=past_days)
    out = []
    for e in events:
        if not e["date"]:
            continue                       # undated rows are not useful on a calendar
        try:
            last = date.fromisoformat(e["end_date"] or e["date"])
        except ValueError:
            continue
        if last >= cutoff:
            out.append(e)
    return out


def load_seen() -> dict:
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("seen.json unreadable, starting fresh")
    return {}


def apply_first_seen(events: list[dict], seen: dict) -> dict:
    today = today_tw()
    for e in events:
        rec = seen.get(e["id"])
        if rec is None:
            rec = {"f": today, "l": today}
            seen[e["id"]] = rec
        else:
            rec["l"] = today
        e["first_seen"] = rec["f"]
    # prune ids not observed for a long time
    limit = (date.fromisoformat(today) - timedelta(days=SEEN_KEEP_DAYS)).isoformat()
    return {k: v for k, v in seen.items() if v.get("l", today) >= limit}


def run(sources=None, dry_run=False, past_days=7) -> list[dict]:
    targets = sources or list(ALL_SCRAPERS.keys())
    all_events, stats = [], {}
    for name in targets:
        if name not in ALL_SCRAPERS:
            log.warning("Unknown source: %s (valid: %s)", name, list(ALL_SCRAPERS))
            continue
        log.info("━━━ %s ━━━", name)
        try:
            evs = ALL_SCRAPERS[name]()
        except Exception as exc:                      # noqa: BLE001
            log.error("✗ %s failed: %s", name, exc, exc_info=True)
            evs = []
        stats[name] = len(evs)
        all_events.extend(evs)

    unique = dedup(all_events)
    window = filter_window(unique, past_days)
    window.sort(key=lambda e: (e["date"], e.get("time") or "99:99", e["title"]))

    seen = load_seen()
    seen = apply_first_seen(window, seen)

    print("\n" + "=" * 58)
    print("  CHEST RADAR — scrape summary")
    print("=" * 58)
    for name, n in stats.items():
        print(f"  {name:<10} {n:>4}")
    hosp = sum(1 for e in window if e["level"] == "hospital")
    print(f"  {'TOTAL':<10} {len(unique):>4} unique | {len(window):>4} in window "
          f"({len(window) - hosp} 學會級 / {hosp} 各院討論會)")
    print("=" * 58 + "\n")

    if not dry_run:
        DATA_DIR.mkdir(exist_ok=True)
        output = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total": len(window),
            "sources": stats,
            "events": window,
        }
        OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")
        SEEN_FILE.write_text(json.dumps(seen, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        log.info("Saved %d events → %s", len(window), OUTPUT_FILE)
    return window


def main():
    p = argparse.ArgumentParser(description="Chest Radar scraper")
    p.add_argument("--sources", nargs="+", metavar="SRC", help=f"default: all {list(ALL_SCRAPERS)}")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--past-days", type=int, default=7)
    p.add_argument("--all-history", action="store_true")
    a = p.parse_args()
    run(sources=a.sources, dry_run=a.dry_run, past_days=99999 if a.all_history else a.past_days)


if __name__ == "__main__":
    main()
