#!/usr/bin/env python3
"""
Claude Code Token Tracker — daily entry point.
Run manually or via launchd (installed by install_schedule.sh).

Usage:
    python daily_report.py            # full run: parse → save → Discord
    python daily_report.py --dry-run  # parse + print, no save/send
    python daily_report.py --stats    # print stats only
"""
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from tracker.api_usage import fetch_real_usage
from tracker.usage     import sum_tokens_for_week
from tracker.stats     import build_stats
from tracker.storage   import save_snapshot, init_db
from tracker.discord   import send_daily_report

WEEK_START_DOW   = int(os.getenv("WEEK_START_DAY",  "0"))   # 0 = Monday
WEEK_RESET_HOUR  = int(os.getenv("WEEK_RESET_HOUR", "0"))   # 9 = 09:00


def _print_stats(s: dict) -> None:
    print("\n" + "=" * 60)
    print(f"  Claude Code Token Report — {s['today'].strftime('%A %d %b %Y')}")
    print(f"  Week day {s['day_of_week']}/7  ·  Grade: {s['pace_grade']}  ·  Budget: {s['budget_source']}")
    print("=" * 60)
    src = "account-wide" if "api" in s["budget_source"] else ("API-calibrated" if s["budget_source"] == "calibrated" else "local JSONL")
    print(f"  Used:          {s['tokens_used']:>14,}  ({s['pct_used']}%)  [{src}]")
    print(f"  Budget:        {s['budget']:>14,}")
    print(f"  Ideal by now:  {s['ideal_tokens']:>14,}  ({s['ideal_pct']}%)")
    print(f"  Pace score:    {s['pace_score_pct']:>13.1f}%  (Grade {s['pace_grade']})")
    print("-" * 60)
    print(f"  Daily avg:     {s['daily_avg']:>14,}")
    print(f"  Daily target:  {s['daily_target']:>14,}")
    print(f"  Projected:     {s['projected_total']:>14,}  ({s['projected_pct']}%)")
    print(f"  Resets in:     {s['reset_in_str']:>14}")
    print(f"  Streak:        {s['streak']:>13} day(s)")
    print(f"  ~Conversations:{s['human_convos']:>14}")
    if s.get("wow"):
        w = s["wow"]
        sign = "+" if w["diff_pct"] >= 0 else ""
        print("-" * 60)
        print(f"  vs last week:  {sign}{w['diff_pct']}%  (was {w['prev_pct']}%)")
    print("=" * 60)
    if s["daily_breakdown"]:
        print("  Daily breakdown:")
        for day_iso, toks in sorted(s["daily_breakdown"].items()):
            print(f"    {day_iso}  {toks:>12,}")
    print()


def run(dry_run: bool = False, stats_only: bool = False) -> None:
    print("[tracker] Fetching real account-wide usage from Anthropic API…")
    api_usage = fetch_real_usage()
    if api_usage:
        print(f"[tracker] API: {api_usage['utilization_7d']:.1%} used  |  "
              f"resets {api_usage['reset_7d'].strftime('%a %Y-%m-%d %H:%M UTC') if api_usage['reset_7d'] else '?'}")
    else:
        print("[tracker] API usage unavailable — using local JSONL only")

    print("[tracker] Parsing Claude Code session files…")
    raw = sum_tokens_for_week(
        week_start_dow=WEEK_START_DOW,
        week_reset_hour=WEEK_RESET_HOUR,
    )
    print(f"[tracker] Scanned {raw['files_scanned']} JSONL files")
    print(f"[tracker] Local tokens this week: {raw['total_tokens']:,}")

    stats = build_stats(
        tokens_used=raw["total_tokens"],
        input_tokens=raw["input_tokens"],
        output_tokens=raw["output_tokens"],
        cache_tokens=raw["cache_creation_tokens"],
        week_start=raw["week_start"],
        week_end=raw["week_end"],
        daily_breakdown=raw["daily_breakdown"],
        detected_limit=raw["detected_limit"],
        week_start_dow=WEEK_START_DOW,
        week_reset_hour=WEEK_RESET_HOUR,
        api_usage=api_usage,
    )

    _print_stats(stats)

    if stats_only:
        return

    if not dry_run:
        init_db()
        save_snapshot(
            tokens_used=stats["local_tokens"],   # always save raw JSONL count for daily breakdown
            input_tokens=stats["input_tokens"],
            output_tokens=stats["output_tokens"],
            cache_tokens=stats["cache_tokens"],
            week_start=stats["week_start"],
            daily_breakdown=stats["daily_breakdown"],
        )
        print("[tracker] Snapshot saved to DB")

        ok = send_daily_report(stats)
        print(f"[tracker] Discord: {'sent ✓' if ok else 'FAILED ✗'}")
    else:
        print("[tracker] --dry-run: skipped DB save and Discord send")


if __name__ == "__main__":
    dry   = "--dry-run" in sys.argv
    only  = "--stats"   in sys.argv
    run(dry_run=dry, stats_only=only)
