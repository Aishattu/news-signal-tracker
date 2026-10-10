#!/usr/bin/env python3
"""
Round-robin lead router: assigns each new lead to the next SDR and posts it to a Slack channel
with the SDR's name on it.

- SDR names (rotation order) live in sdrs.json. An SDR's "slack_user_id" is optional;
  if set, the post @mentions them instead of using plain text.
- The Slack webhook in .env decides which workspace + channel the posts go to
  (one webhook per tracker, so a client tracker posts into the client's Slack).
- Whose turn it is lives in state/round_robin.json, so the rotation carries over
  between daily runs (3 leads today = Sarah, John, Sarah; tomorrow starts with John).
- Results are written back into the leads CSV as new columns:
  Assigned SDR, Assigned At, Slack Status. Rows that already have an Assigned SDR are skipped,
  so running it twice never double-sends.
- The turn only moves forward after the post is sent. If Slack fails, the lead stays
  unassigned and the next run retries it.

Run:
    python route_leads.py --dry-run          # show who gets what, send nothing
    python route_leads.py                    # newest output/leads_*.csv
    python route_leads.py output/leads_2026-10-03.csv

Needs SLACK_WEBHOOK_URL in .env (Slack app > Incoming Webhooks > Add New Webhook).
"""

from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent
SDRS_FILE = BASE / "sdrs.json"
STATE_FILE = BASE / "state" / "round_robin.json"
NEW_COLS = ["Assigned SDR", "Assigned At", "Slack Status"]


def load_env():
    env = BASE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def post(webhook: str, text: str):
    req = urllib.request.Request(
        webhook,
        data=json.dumps({"text": text, "unfurl_links": False}).encode(),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read().decode()
    if body != "ok":
        raise RuntimeError(f"Slack webhook replied: {body}")


def lead_message(row: dict, sdr: dict) -> str:
    who = f"<@{sdr['slack_user_id']}>" if sdr.get("slack_user_id") else f"*{sdr['name']}*"
    verified = row.get("Email Verification", "").lower().startswith("valid")
    email = row.get("Email") or "NOT FOUND"
    email_line = email if verified else f"{email}  :warning: not verified yet, check before sending"
    return "\n".join([
        f"New lead for {who} :dart:",
        f"*{row.get('Decision Maker', 'NOT FOUND')}*, {row.get('Title', '')} at *{row.get('Company', '')}*",
        f"• Email: {email_line}",
        f"• LinkedIn: {row.get('LinkedIn') or 'NOT FOUND'}",
        f"• News ({row.get('News Date', '')}): <{row.get('News Link', '')}|{row.get('News Headline', '')}>",
    ]).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", help="leads CSV (default: newest output/leads_*.csv)")
    ap.add_argument("--dry-run", action="store_true", help="print assignments, send and save nothing")
    args = ap.parse_args()

    path = Path(args.csv) if args.csv else max((BASE / "output").glob("leads_*.csv"), default=None)
    if not path or not path.exists():
        sys.exit("[route] no leads CSV found")

    cfg = json.loads(SDRS_FILE.read_text())
    sdrs = cfg.get("sdrs", [])
    if not sdrs:
        sys.exit("[route] sdrs.json has no SDRs")
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"next_index": 0, "log": []}

    load_env()
    webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not args.dry_run and not webhook.startswith("https://hooks.slack.com/"):
        sys.exit("[route] STOPPED: SLACK_WEBHOOK_URL missing or wrong in .env. Nothing sent.")

    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    cols = list(rows[0].keys()) if rows else []
    cols += [c for c in NEW_COLS if c not in cols]

    sent = failed = 0
    for row in rows:
        if row.get("Assigned SDR"):
            continue
        sdr = sdrs[state["next_index"] % len(sdrs)]
        text = lead_message(row, sdr)
        if args.dry_run:
            print(f"--- would post for {sdr['name']} ---\n{text}\n")
            state["next_index"] += 1
            continue
        try:
            post(webhook, text)
        except Exception as e:
            row["Slack Status"] = f"FAILED: {e}"
            failed += 1
            print(f"[route] {row.get('Company')}: Slack failed ({e}); left unassigned, will retry next run")
            continue
        now = dt.datetime.now().isoformat(timespec="seconds")
        row.update({"Assigned SDR": sdr["name"], "Assigned At": now, "Slack Status": "sent"})
        state["next_index"] += 1
        state["log"].append({"at": now, "sdr": sdr["name"], "company": row.get("Company"), "csv": path.name})
        sent += 1
        print(f"[route] {row.get('Company')} -> {sdr['name']}")

    if args.dry_run:
        print("[route] dry run: nothing sent, nothing saved")
        return

    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in cols} for r in rows)
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1))
    print(f"[route] sent {sent}, failed {failed}, next up: {sdrs[state['next_index'] % len(sdrs)]['name']}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
