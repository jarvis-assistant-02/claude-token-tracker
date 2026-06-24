# Claude Token Tracker

Daily Discord reports on your Claude Code weekly token usage — with a real chart and military-brief stats card.

## Examples

**Grade D — below pace (day 3 of 7, 19% used, should be 43%)**

![Grade D chart](docs/sample_grade_d.png)

**Grade A — crushing it (day 5 of 7, 74% used, ahead of pace)**

![Grade A chart](docs/sample_grade_a.png)

**Discord message (paired with the chart above):**

```
DAY 3/7   WEEK 26   Wed 24 Jun

STATUS       D  — well behind
USED         963K / 5.07M   (19.0%)
SHOULD BE    42.9%   (gap: 23.9 pts)
TARGET       1.03M tokens today
RESETS       Monday in 5d 7h
FORECAST     44% end of week
STREAK       1 day above pace
```

---

## What it does

- Reads real account-wide usage from the Anthropic API rate-limit headers (macOS)
- Parses `~/.claude/projects/**/*.jsonl` for the daily breakdown bar chart
- Auto-calibrates your weekly budget from the API utilisation %
- Sends a Discord embed every evening: % used, pace grade (A–F), daily target, projection, countdown to reset, week-over-week comparison, streak

## Requirements

- macOS (the launchd scheduler and keychain read are macOS-only)
- Claude Code installed and signed in
- Python 3.11+
- A Discord server where you can create a webhook

## Setup

```bash
git clone https://github.com/jarvis-assistant-02/claude-token-tracker
cd claude-token-tracker

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — at minimum fill in DISCORD_WEBHOOK_URL
```

**Create the Discord webhook:**
1. Discord server → Settings → Integrations → Webhooks → New Webhook
2. Assign it to a channel (e.g. `#claude-tokens`)
3. Copy the URL → paste as `DISCORD_WEBHOOK_URL` in `.env`

**Install the daily schedule:**
```bash
bash install_schedule.sh
```
This installs a launchd agent that runs every day at the hour set by `REPORT_HOUR` in `.env` (default 19:00). If the machine was asleep at that time, launchd fires it on the next wake.

## Test it

```bash
source .venv/bin/activate
python daily_report.py --dry-run   # prints stats, skips DB save and Discord send
python daily_report.py             # full run: saves snapshot + sends Discord
```

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | — | **Required.** Webhook URL for your Discord channel |
| `WEEKLY_TOKEN_BUDGET` | auto | Leave empty for auto-detection. Set manually if you know your plan's exact limit |
| `WEEK_START_DAY` | `0` | Day the week resets: 0 = Monday |
| `WEEK_RESET_HOUR` | `9` | Local hour (24h) when the week resets. Claude Pro = 9 AM Lisbon / 8 AM UTC |
| `REPORT_HOUR` | `19` | Local hour to send the daily Discord report |

## How usage is calculated

**On macOS**, the tracker makes one minimal Anthropic API call per day (9 tokens) and reads the `anthropic-ratelimit-unified-7d-utilization` header — the same server-side signal that enforces your weekly limit. This gives you the real account-wide percentage, including usage from all devices and claude.ai web. It then cross-references with local JSONL files to produce an accurate budget estimate.

**On other platforms**, or if the API call fails, the tracker falls back to parsing `~/.claude/projects/**/*.jsonl` directly.

## Security

- Your Discord webhook URL is stored only in `.env`, which is gitignored and never committed
- The Anthropic OAuth token is read at runtime from macOS keychain and is never logged, stored, or transmitted anywhere other than `api.anthropic.com`
- The project makes no outbound requests other than one daily Anthropic API call and the Discord webhook POST

## Uninstall

```bash
bash install_schedule.sh --uninstall
```

This removes the launchd agent. You can then delete the project folder.
