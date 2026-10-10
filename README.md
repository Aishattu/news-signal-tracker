# AI Adoption News Tracker

Finds companies in the news that are rolling out AI, finds the right decision maker, gets their verified email and LinkedIn, then hands each lead to the next SDR in a Slack channel.

## How it works

1. **Fetch** – `fetch_news.py` pulls the last 14 days of headlines from press wires and news sites (`config.json`).
2. **Filter** – real "company X adopts AI" stories are kept; vendor launches, funding, surveys and promos are dropped.
3. **Enrich** – the current decision maker is found and checked, then `email_waterfall.sh` finds and verifies their email through Clay.
4. **Route** – `route_leads.py` posts each lead to Slack, taking turns between SDRs (`sdrs.json`). The rotation carries over day to day.

## Sample Slack post

![Sample Slack post](assets/sample-slack-post.png)

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install feedparser
cp .env.example .env   # add your Slack webhook
```

Requires the `clay` CLI (logged in) for email lookups.

## Run

```bash
.venv/bin/python fetch_news.py --days 14
.venv/bin/python route_leads.py --dry-run   # preview
.venv/bin/python route_leads.py             # post to Slack
```
