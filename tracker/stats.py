"""
Calculate all derived stats from raw token counts and stored history.
"""
import os
from datetime import date, datetime, timezone, timedelta
from tracker.storage import (
    get_peak_weekly_tokens,
    get_budget,
    set_budget,
    get_same_day_last_week,
)

# Default budget for Claude Code Max 5x plan (~225M tokens/week).
# Auto-calibrates over time from observed peaks and detected limits.
_DEFAULT_BUDGET = 225_000_000


def get_effective_budget(detected_limit: int | None = None) -> tuple[int, str]:
    """
    Return (budget_tokens, source) where source is one of:
      'env'       — set explicitly via WEEKLY_TOKEN_BUDGET env var
      'detected'  — inferred from a rate-limit error this week
      'observed'  — highest weekly total ever recorded in DB
      'default'   — fallback hardcoded value (Max 5x plan)

    Also persists any newly detected limit for future reference.
    """
    # 1. Explicit env override always wins
    env_val = os.getenv("WEEKLY_TOKEN_BUDGET")
    if env_val:
        try:
            return int(env_val), "env"
        except ValueError:
            pass

    # 2. Rate-limit detected this session
    if detected_limit and detected_limit > 0:
        set_budget("detected_limit", str(detected_limit))
        return detected_limit, "detected"

    # 3. Previously persisted detected limit
    stored = get_budget("detected_limit")
    if stored:
        try:
            return int(stored), "detected"
        except ValueError:
            pass

    # 4. Highest ever observed weekly total (lower bound on true budget)
    peak = get_peak_weekly_tokens()
    if peak > 0:
        # Use 110% of observed peak as a reasonable estimate
        return int(peak * 1.10), "observed"

    return _DEFAULT_BUDGET, "default"


def build_stats(
    tokens_used: int,
    input_tokens: int,
    output_tokens: int,
    cache_tokens: int,
    week_start: datetime,
    daily_breakdown: dict,
    detected_limit: int | None = None,
    week_start_dow: int = 0,
) -> dict:
    """
    Returns a comprehensive stats dict for the daily report.
    """
    budget, budget_source = get_effective_budget(detected_limit)
    today = date.today()
    week_start_date = week_start.date()

    day_of_week = (today - week_start_date).days + 1  # 1-based
    days_elapsed = max(day_of_week, 1)
    days_remaining = max(7 - day_of_week, 0)
    days_in_week = 7

    pct_used = (tokens_used / budget * 100) if budget > 0 else 0.0
    pct_elapsed = (days_elapsed / days_in_week) * 100

    # Ideal pace: linear distribution across 7 days
    ideal_pct_by_now = pct_elapsed
    ideal_tokens_by_now = int(budget * days_elapsed / days_in_week)

    # Projection: extrapolate current rate to end of week
    daily_avg = tokens_used / days_elapsed if days_elapsed > 0 else 0
    projected_total = int(daily_avg * days_in_week)
    projected_pct = (projected_total / budget * 100) if budget > 0 else 0.0

    # Daily target to hit 100% by end of week
    tokens_remaining = budget - tokens_used
    daily_target = int(tokens_remaining / days_remaining) if days_remaining > 0 else 0
    multiplier = (daily_target / daily_avg) if daily_avg > 0 else float("inf")

    # Status signal
    if projected_pct >= 95:
        status = "on_track"
    elif projected_pct >= 70:
        status = "slightly_low"
    else:
        status = "under_using"

    # Week-over-week comparison
    same_day_last = get_same_day_last_week(today.isoformat())
    wow = None
    if same_day_last:
        prev_pct = (same_day_last["tokens_used"] / budget * 100)
        diff_pct = pct_used - prev_pct
        wow = {
            "prev_tokens": same_day_last["tokens_used"],
            "prev_pct": round(prev_pct, 1),
            "diff_pct": round(diff_pct, 1),
            "ahead": diff_pct >= 0,
        }

    return {
        "budget": budget,
        "budget_source": budget_source,
        "tokens_used": tokens_used,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_tokens": cache_tokens,
        "tokens_remaining": tokens_remaining,
        "pct_used": round(pct_used, 1),
        "pct_elapsed": round(pct_elapsed, 1),
        "ideal_pct_by_now": round(ideal_pct_by_now, 1),
        "ideal_tokens_by_now": ideal_tokens_by_now,
        "day_of_week": day_of_week,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "daily_avg": int(daily_avg),
        "daily_target": daily_target,
        "multiplier": round(multiplier, 1),
        "projected_total": projected_total,
        "projected_pct": round(projected_pct, 1),
        "status": status,
        "week_start": week_start,
        "daily_breakdown": daily_breakdown,
        "wow": wow,
        "today": today,
    }
