# Claude Token Tracker — CLAUDE.md

## Purpose
Tracks weekly Claude Code token usage. Sends a daily Discord report at 19:00 to `#claude-tokens`
reminding the user to maximise token spending before the weekly budget resets (Monday 08:00 UTC
for the Pro plan, which is Monday 09:00 Lisbon / 04:00 ET).

## Stack
- Python 3.11+ with virtualenv at `.venv/`
- `requests` — Discord webhook POST + Anthropic API probe
- `python-dotenv` — env var loading
- `sqlite3` (stdlib) — daily snapshots at `data/tracker.db`
- macOS `launchd` — daily trigger via `~/Library/LaunchAgents/`

## Architecture
```
daily_report.py          # entry point (launchd runs this)
tracker/
  api_usage.py           # read real account-wide % from Anthropic API headers (macOS only)
  usage.py               # parse ~/.claude JSONL → daily token breakdown
  stats.py               # derive %, projection, daily target, week-over-week
  storage.py             # SQLite: save/read daily snapshots + budget config
  discord.py             # build Discord embeds + POST to webhook
  chart.py               # matplotlib ring + bar chart (style 2A)
data/
  tracker.db             # SQLite DB (gitignored)
  tracker.log            # stdout log from launchd (gitignored)
install_schedule.sh      # installs/uninstalls the launchd plist
```

## Setup (one-time)
```bash
cd ~/Desktop/Projects/claude-token-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# copy .env.example → .env and fill in:
#   DISCORD_WEBHOOK_URL  — webhook for #claude-tokens channel

bash install_schedule.sh   # installs launchd; reads REPORT_HOUR from .env (default 19)
```

## Commands
```bash
source .venv/bin/activate

python daily_report.py            # full run: parse → save → send Discord
python daily_report.py --dry-run  # parse + print stats, no save/send
python daily_report.py --stats    # print stats only (no DB, no Discord)

bash install_schedule.sh           # install launchd (default 19:00)
bash install_schedule.sh --uninstall
```

## Token Budget Detection (priority order)
1. `WEEKLY_TOKEN_BUDGET` env var (manual override)
2. Auto-calibrated: divides local JSONL token count by the real API utilisation %
   — reveals the true budget without ever hitting the limit
3. Rate-limit error detected from JSONL files
4. 110% of highest completed-week total in `tracker.db`
5. Fallback: 50,000,000 (Pro plan rough estimate)

## Real Usage via API Headers
On macOS, the tracker makes one minimal API call per day and reads:
  `anthropic-ratelimit-unified-7d-utilization` — real account-wide weekly % used
  `anthropic-ratelimit-unified-7d-reset`       — exact reset Unix timestamp

This is the same enforcement signal that gates access when you hit 100%.
It covers usage from all devices, claude.ai web, and Claude Code sessions.
The OAuth token is read from macOS keychain (`Claude Code-credentials`) and
never logged or stored anywhere. On Linux/Windows this step is skipped and
the tracker falls back to local JSONL parsing only.

## Discord Setup
1. Discord server → Settings → Integrations → Webhooks → New Webhook
2. Assign to `#claude-tokens`
3. Copy URL → `.env` as `DISCORD_WEBHOOK_URL`

## Week Reset
Pro plan: Monday 08:00 UTC (Monday 09:00 Lisbon, 04:00 ET).
Override day via `WEEK_START_DAY` (0=Monday) and hour via `WEEK_RESET_HOUR` in `.env`.
