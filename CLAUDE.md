# Claude Token Tracker — CLAUDE.md

## Purpose
Tracks weekly Claude Code token usage by parsing `~/.claude/projects/**/*.jsonl` files.
Sends a rich daily Discord report at 09:00 to `#claude-tokens` reminding the user to
maximize token spending before the weekly budget resets (Monday 00:00 UTC by default).

## Stack
- Python 3.11+ with virtualenv at `.venv/`
- `requests` — Discord webhook POST
- `python-dotenv` — env var loading
- `sqlite3` (stdlib) — daily snapshots at `data/tracker.db`
- macOS `launchd` — daily 09:00 trigger via `~/Library/LaunchAgents/`

## Architecture
```
daily_report.py          # entry point (launchd runs this)
tracker/
  usage.py               # parse ~/.claude JSONL → token sums for current week
  stats.py               # derive %, projection, daily target, week-over-week
  storage.py             # SQLite: save/read daily snapshots + budget config
  discord.py             # build Discord embeds + POST to webhook
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
#   WEEKLY_TOKEN_BUDGET  — leave empty for auto-detect

# Install daily 09:00 schedule
bash install_schedule.sh
```

## Commands
```bash
source .venv/bin/activate

python daily_report.py            # full run: parse → save → send Discord
python daily_report.py --dry-run  # parse + print stats, no save/send
python daily_report.py --stats    # print stats only (no DB, no Discord)

bash install_schedule.sh           # install launchd (runs daily 09:00)
bash install_schedule.sh --uninstall
```

## Token Budget Auto-Detection
The budget is determined in priority order:
1. `WEEKLY_TOKEN_BUDGET` env var (manual override — most accurate)
2. Rate-limit error detected from JSONL files (auto-saved to DB)
3. 110% of the highest weekly total ever recorded in `tracker.db`
4. Fallback: 225,000,000 (Max 5x plan estimate)

To calibrate: just use Claude Code normally. After the first week where you hit
the limit, the system learns it automatically. You can always hard-code it in `.env`.

## Discord Setup
1. In your Discord server: `Settings → Integrations → Webhooks → New Webhook`
2. Assign it to channel `#claude-tokens`
3. Copy the URL → paste into `.env` as `DISCORD_WEBHOOK_URL`

## Week Reset Day
Default: Monday 00:00 UTC.
Change via `WEEK_START_DAY` in `.env` (0=Monday, 6=Sunday).
