"""
Parse ~/.claude/projects/**/*.jsonl to sum token usage for the current (or any) week.
Counts: input_tokens + output_tokens + cache_creation_input_tokens.
cache_read_input_tokens are excluded — they don't consume new capacity.
"""
import glob
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


CLAUDE_DIR = Path.home() / ".claude" / "projects"


def _week_bounds(
    week_start_dow: int = 0,
    week_reset_hour: int = 0,
) -> tuple[datetime, datetime]:
    """
    Return (week_start, week_end) as UTC-aware datetimes for the current week.

    week_start_dow : 0=Monday … 6=Sunday
    week_reset_hour: hour of day (local time) when the week resets (e.g. 9 = 09:00)
    """
    local_now = datetime.now()
    days_since_start = (local_now.weekday() - week_start_dow) % 7

    # Candidate: this week's reset moment in local time
    candidate = (local_now - timedelta(days=days_since_start)).replace(
        hour=week_reset_hour, minute=0, second=0, microsecond=0
    )
    # If we're before the reset moment (e.g. Monday 08:45 when reset is 09:00)
    if local_now < candidate:
        candidate -= timedelta(days=7)

    end = candidate + timedelta(days=7)

    # Convert to UTC-aware so we can compare with JSONL timestamps
    local_tz = datetime.now().astimezone().tzinfo
    start_utc = candidate.replace(tzinfo=local_tz).astimezone(timezone.utc)
    end_utc   = end.replace(tzinfo=local_tz).astimezone(timezone.utc)
    return start_utc, end_utc


def _tokens_from_entry(entry: dict) -> int:
    msg = entry.get("message", {})
    if not isinstance(msg, dict):
        return 0
    usage = msg.get("usage", {})
    if not isinstance(usage, dict):
        return 0
    return (
        usage.get("input_tokens", 0)
        + usage.get("output_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
    )


def _parse_timestamp(entry: dict) -> datetime | None:
    ts = entry.get("timestamp")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def sum_tokens_for_week(
    week_start: datetime | None = None,
    week_end: datetime | None = None,
    week_start_dow: int = 0,
    week_reset_hour: int = 0,
) -> dict:
    """
    Parse all JSONL files under CLAUDE_DIR and return:
      total_tokens, input_tokens, output_tokens, cache_creation_tokens,
      files_scanned, week_start, week_end,
      daily_breakdown (ISO date → tokens),
      detected_limit (int | None)
    """
    if week_start is None or week_end is None:
        week_start, week_end = _week_bounds(week_start_dow, week_reset_hour)

    total = input_t = output_t = cache_t = 0
    files_scanned = 0
    daily: dict[str, int] = {}
    detected_limit: int | None = None

    pattern = str(CLAUDE_DIR / "**" / "*.jsonl")
    for fpath in glob.iglob(pattern, recursive=True):
        files_scanned += 1
        try:
            with open(fpath, encoding="utf-8", errors="ignore") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        entry = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    # Detect rate-limit error to auto-calibrate budget
                    if detected_limit is None:
                        err = entry.get("error") or (entry.get("message", {}) or {}).get("error")
                        if isinstance(err, dict) and "rate" in str(err.get("type", "")).lower():
                            detected_limit = total

                    ts = _parse_timestamp(entry)
                    if ts is None or not (week_start <= ts < week_end):
                        continue

                    t = _tokens_from_entry(entry)
                    if t == 0:
                        continue

                    msg   = entry.get("message", {}) or {}
                    usage = msg.get("usage", {}) or {}
                    input_t += usage.get("input_tokens", 0)
                    output_t += usage.get("output_tokens", 0)
                    cache_t  += usage.get("cache_creation_input_tokens", 0)
                    total    += t

                    day_key = ts.astimezone(datetime.now().astimezone().tzinfo).date().isoformat()
                    daily[day_key] = daily.get(day_key, 0) + t

        except (OSError, PermissionError):
            pass

    return {
        "total_tokens": total,
        "input_tokens": input_t,
        "output_tokens": output_t,
        "cache_creation_tokens": cache_t,
        "files_scanned": files_scanned,
        "week_start": week_start,
        "week_end": week_end,
        "daily_breakdown": daily,
        "detected_limit": detected_limit,
    }
