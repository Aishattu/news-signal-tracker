#!/usr/bin/env python3
"""
News Tracker – fetch step (generic, config-driven).

Pulls candidate headlines from the monitored sites two ways:
  1. Each site's own RSS feed (if one is listed in config.json) – newest items only.
  2. Google News RSS pinned to each site + each signal query, over the lookback window.
     This is what finds most real signal news; direct feeds only hold the last few days.

It does NOT decide what counts as a signal. It writes every candidate to a CSV,
drops obvious noise via config "exclude_patterns", and leaves the judgment step
(reading articles, confirming the signal) to Claude.

Run:    python fetch_news.py [--days N]
Input:  config.json (same folder)
Output: output/candidates_YYYY-MM-DD.csv
"""

from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import re
import time
import urllib.parse as up
from pathlib import Path

import feedparser

BASE = Path(__file__).parent
OUTPUT_DIR = BASE / "output"
STATE_DIR = BASE / "state"
OUTPUT_DIR.mkdir(exist_ok=True)
STATE_DIR.mkdir(exist_ok=True)

TODAY = dt.date.today()


def entry_date(e) -> dt.date | None:
    pd = e.get("published_parsed") or e.get("updated_parsed")
    return dt.date(*pd[:3]) if pd else None


def main():
    cfg = json.loads((BASE / "config.json").read_text())
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=cfg.get("lookback_days", 7))
    args = ap.parse_args()

    cutoff = TODAY - dt.timedelta(days=args.days)
    exclude = re.compile("|".join(cfg.get("exclude_patterns", [])) or r"(?!x)x", re.I)
    include = re.compile("|".join(cfg.get("headline_must_match", [])) or r".", re.I)
    reported = set()
    rep_file = STATE_DIR / "reported_companies.json"
    if rep_file.exists():
        reported = {c.lower() for c in json.loads(rep_file.read_text())}

    rows, seen_titles = [], set()

    def add(site: str, method: str, e):
        title = re.sub(r"\s+-\s+[^-]+$", "", e.get("title", "")).strip()  # strip " - Business Wire"
        if not title or title.lower() in seen_titles:
            return
        d = entry_date(e)
        if d and d < cutoff:
            return
        if exclude.search(title) or not include.search(title):
            return
        if any(c in title.lower() for c in reported):
            return
        seen_titles.add(title.lower())
        rows.append({
            "date": d.isoformat() if d else "",
            "site": site,
            "method": method,
            "headline": title,
            "link": e.get("link", ""),
        })

    # 1. Direct RSS feeds
    for s in cfg["sites"]:
        if s.get("rss"):
            try:
                for e in feedparser.parse(s["rss"]).entries:
                    add(s["domain"], "rss", e)
            except Exception as ex:
                print(f"  {s['domain']} rss ERROR: {ex}")

    # 2. Google News site-pinned signal queries (sleep between calls to avoid rate limits)
    for s in cfg["sites"]:
        n_before = len(rows)
        for q in cfg["signal_queries"]:
            url = ("https://news.google.com/rss/search?q="
                   + up.quote(f"site:{s['domain']} {q} when:{args.days}d")
                   + "&hl=en-US&gl=US&ceid=US:en")
            try:
                for e in feedparser.parse(url).entries:
                    add(s["domain"], "gnews", e)
            except Exception as ex:
                print(f"  {s['domain']} gnews ERROR: {ex}")
            time.sleep(1.5)
        print(f"  {s['domain']}: {len(rows) - n_before} candidates")

    rows.sort(key=lambda r: r["date"], reverse=True)
    out = OUTPUT_DIR / f"candidates_{TODAY.isoformat()}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "site", "method", "headline", "link"])
        w.writeheader()
        w.writerows(rows)
    print(f"[fetch] {len(rows)} candidates ({args.days}-day window) -> {out}")


if __name__ == "__main__":
    main()
