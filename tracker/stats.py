"""
Calculate all derived stats from raw token counts and stored history.
"""
import os
from datetime import date, datetime, timedelta, timezone
from tracker.storage import (
    get_peak_weekly_tokens,
    get_budget,
    set_budget,
    get_same_day_last_week,
    get_streak,
)

# Claude Code Pro plan estimated weekly budget.
# Auto-calibrates over time from observed peaks and detected limits.
_DEFAULT_BUDGET = 50_000_000  # ~50M tokens (Pro plan estimate)

# Rough average tokens per "long Claude conversation" — used for human context
_AVG_CONVO_TOKENS = 75_000


def get_effective_budget(detected_limit: int | None = None) -> tuple[int, str]:
    """
    Return (budget_tokens, source):
      'env'      — explicit WEEKLY_TOKEN_BUDGET env var
      'detected' — inferred from a rate-limit error
      'observed' — 110% of the highest completed-week total
      'default'  — Pro plan estimate (50M)
    """
    env_val = os.getenv("WEEKLY_TOKEN_BUDGET")
    if env_val:
        try:
            return int(env_val), "env"
        except ValueError:
            pass

    if detected_limit and detected_limit > 0:
        set_budget("detected_limit", str(detected_limit))
        return detected_limit, "detected"

    stored = get_budget("detected_limit")
    if stored:
        try:
            return int(stored), "detected"
        except ValueError:
            pass

    peak = get_peak_weekly_tokens()
    if peak > 0:
        return int(peak * 1.10), "observed"

    return _DEFAULT_BUDGET, "default"


def _pace_grade(pace_score_pct: float) -> str:
    if pace_score_pct >= 90:  return "A"
    if pace_score_pct >= 75:  return "B"
    if pace_score_pct >= 50:  return "C"
    if pace_score_pct >= 25:  return "D"
    return "F"


def _reset_countdown(week_end: datetime) -> str:
    now = datetime.now(timezone.utc)
    delta = week_end - now
    if delta.total_seconds() <= 0:
        return "now"
    days    = delta.days
    hours   = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def build_stats(
    tokens_used: int,
    input_tokens: int,
    output_tokens: int,
    cache_tokens: int,
    week_start: datetime,
    week_end: datetime,
    daily_breakdown: dict,
    detected_limit: int | None = None,
    week_start_dow: int = 0,
    week_reset_hour: int = 0,
    api_usage: dict | None = None,
) -> dict:
    budget, budget_source = get_effective_budget(detected_limit)
    today = date.today()

    # If the API gave us a precise reset timestamp, use it — more accurate than JSONL bounds
    if api_usage and api_usage.get("reset_7d"):
        week_end = api_usage["reset_7d"]

    week_start_date = week_start.astimezone(datetime.now().astimezone().tzinfo).date()

    day_of_week   = (today - week_start_date).days + 1   # 1-based
    days_elapsed  = max(day_of_week, 1)
    days_remaining = max(7 - day_of_week, 0)

    # Real account-wide utilisation from API headers (preferred over local JSONL ratio)
    local_pct = (tokens_used / budget * 100) if budget > 0 else 0.0
    if api_usage and api_usage.get("utilization_7d") is not None:
        util = api_usage["utilization_7d"]
        pct_used = round(util * 100, 2)
        # If local tokens ≈ account-wide (within 20%) and budget source is default,
        # calibrate the real budget from: budget = local_tokens / utilization
        if budget_source == "default" and util > 0.01 and tokens_used > 0:
            inferred = int(tokens_used / util)
            if inferred < budget * 0.5:
                # Inferred is substantially lower → Pro plan is smaller than 50M estimate
                budget = inferred
                budget_source = "calibrated"
            else:
                budget_source = budget_source + "+api"
        else:
            budget_source = budget_source + "+api"
        tokens_used_display = int(budget * util)
    else:
        pct_used = local_pct
        tokens_used_display = tokens_used

    pct_elapsed  = (days_elapsed / 7) * 100
    ideal_pct    = pct_elapsed
    ideal_tokens = int(budget * days_elapsed / 7)

    # Pace score: how well you're keeping up with ideal pace (100% = perfect)
    pace_score_pct = (pct_used / ideal_pct * 100) if ideal_pct > 0 else 0.0
    pace_grade     = _pace_grade(pace_score_pct)

    daily_avg       = tokens_used_display / days_elapsed if days_elapsed > 0 else 0
    projected_total = int(daily_avg * 7)
    projected_pct   = (projected_total / budget * 100) if budget > 0 else 0.0

    tokens_remaining = budget - tokens_used_display
    daily_target     = int(tokens_remaining / days_remaining) if days_remaining > 0 else 0

    # Status signal based on projected end-of-week %
    if projected_pct >= 95:
        status = "on_track"
    elif projected_pct >= 70:
        status = "slightly_low"
    else:
        status = "under_using"

    # Human context
    human_convos = max(0, int(max(tokens_remaining, 0) / _AVG_CONVO_TOKENS))

    # Countdown to reset
    reset_in_str = _reset_countdown(week_end)

    # Streak: consecutive days this week where daily tokens >= ideal daily target
    ideal_daily = budget / 7
    streak = get_streak(daily_breakdown, ideal_daily, week_start_date)

    # Week-over-week
    same_day_last = get_same_day_last_week(today.isoformat())
    wow = None
    if same_day_last:
        prev_pct  = same_day_last["tokens_used"] / budget * 100
        diff_pct  = pct_used - prev_pct
        wow = {
            "prev_tokens": same_day_last["tokens_used"],
            "prev_pct":    round(prev_pct, 1),
            "diff_pct":    round(diff_pct, 1),
            "ahead":       diff_pct >= 0,
        }

    return {
        "budget":            budget,
        "budget_source":     budget_source,
        "tokens_used":       tokens_used_display,
        "local_tokens":      tokens_used,       # raw JSONL count for this machine only
        "local_pct":         round(local_pct, 1),
        "input_tokens":      input_tokens,
        "output_tokens":     output_tokens,
        "cache_tokens":      cache_tokens,
        "tokens_remaining":  tokens_remaining,
        "pct_used":          round(pct_used, 1),
        "pct_elapsed":       round(pct_elapsed, 1),
        "ideal_pct":         round(ideal_pct, 1),
        "ideal_tokens":      ideal_tokens,
        "pace_score_pct":    round(pace_score_pct, 1),
        "pace_grade":        pace_grade,
        "day_of_week":       day_of_week,
        "days_elapsed":      days_elapsed,
        "days_remaining":    days_remaining,
        "daily_avg":         int(daily_avg),
        "daily_target":      daily_target,
        "ideal_daily":       int(ideal_daily),
        "projected_total":   projected_total,
        "projected_pct":     round(projected_pct, 1),
        "status":            status,
        "human_convos":      human_convos,
        "reset_in_str":      reset_in_str,
        "streak":            streak,
        "week_start":        week_start,
        "week_end":          week_end,
        "week_start_date":   week_start_date,
        "daily_breakdown":   daily_breakdown,
        "wow":               wow,
        "today":             today,
    }
