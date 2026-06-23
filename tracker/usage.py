"""
Parse ~/.claude/projects/**/*.jsonl to sum token usage for the current (or any) week.
Counts: input_tokens + output_tokens + cache_creation_input_tokens.
cache_read_input_tokens are intentionally excluded — they don't consume new capacity.
"""
import glob
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


CLAUDE_DIR = Path.home() / ".claude" / "projects"


def _week_bounds(day: datetime | None = None, week_start_dow: int = 0) -> tuple[datetime, datetime]:
    """Return (week_start, week_end) as UTC-aware datetimes for the week containing `day`.
    week_start_dow: 0=Monday, 6=Sunday.
    """
    if day is None:
        day = datetime.now(timezone.utc)
    day = day.replace(tzinfo=timezone.utc) if day.tzinfo is None else day.astimezone(timezone.utc)
    diff = (day.weekday() - week_start_dow) % 7
    start = (day - timedelta(days=diff)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return start, end


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
) -> dict:
    """
    Parse all JSONL files under CLAUDE_DIR and return a dict with:
      - total_tokens: int
      - input_tokens: int
      - output_tokens: int
      - cache_creation_tokens: int
      - files_scanned: int
      - week_start: datetime
      - week_end: datetime
      - daily_breakdown: dict[str, int]  (ISO date string → tokens)
      - detected_limit: int | None  (inferred from rate-limit errors, if any)
    """
    if week_start is None or week_end is None:
        week_start, week_end = _week_bounds(week_start_dow=week_start_dow)

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

                    # Check for rate-limit / max-tokens error to auto-detect budget
                    if detected_limit is None:
                        err = entry.get("error") or (entry.get("message", {}) or {}).get("error")
                        if isinstance(err, dict) and "rate" in str(err.get("type", "")).lower():
                            # Use current total at the time of hitting the limit as a floor
                            detected_limit = total

                    ts = _parse_timestamp(entry)
                    if ts is None or not (week_start <= ts < week_end):
                        continue

                    t = _tokens_from_entry(entry)
                    if t == 0:
                        continue

                    msg = entry.get("message", {}) or {}
                    usage = msg.get("usage", {}) or {}
                    input_t += usage.get("input_tokens", 0)
                    output_t += usage.get("output_tokens", 0)
                    cache_t += usage.get("cache_creation_input_tokens", 0)
                    total += t

                    day_key = ts.date().isoformat()
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


def sum_tokens_for_previous_week(week_start_dow: int = 0) -> dict:
    now = datetime.now(timezone.utc)
    start, end = _week_bounds(now, week_start_dow)
    prev_start = start - timedelta(days=7)
    prev_end = start
    return sum_tokens_for_week(prev_start, prev_end, week_start_dow)
