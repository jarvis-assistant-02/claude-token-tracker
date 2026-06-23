#!/usr/bin/env python3
"""
Claude Code Token Tracker — daily entry point.
Run manually or via launchd (see install_schedule.sh).

Usage:
    python daily_report.py           # full run: parse, save, notify
    python daily_report.py --dry-run # parse and print stats, no Discord send
    python daily_report.py --stats   # print current stats only (no save/send)
"""
import os
import sys
from pathlib import Path

# Load .env from project root
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from tracker.usage import sum_tokens_for_week
from tracker.stats import build_stats
from tracker.storage import save_snapshot, init_db
from tracker.discord import send_daily_report

WEEK_START_DOW = int(os.getenv("WEEK_START_DAY", "0"))  # 0=Monday


def _print_stats(s: dict) -> None:
    print("\n" + "=" * 55)
    print(f"  Claude Code Token Report — {s['today'].strftime('%A %d %b %Y')}")
    print(f"  Week day {s['day_of_week']}/7 · Budget source: {s['budget_source']}")
    print("=" * 55)
    print(f"  Used:         {s['tokens_used']:>14,}  ({s['pct_used']}%)")
    print(f"  Budget:       {s['budget']:>14,}")
    print(f"  Remaining:    {s['tokens_remaining']:>14,}")
    print(f"  Ideal by now: {s['ideal_tokens_by_now']:>14,}  ({s['ideal_pct_by_now']}%)")
    print("-" * 55)
    print(f"  Daily avg:    {s['daily_avg']:>14,}")
    print(f"  Daily target: {s['daily_target']:>14,}")
    print(f"  Projected:    {s['projected_total']:>14,}  ({s['projected_pct']}%)")
    print(f"  Multiplier:   {s['multiplier']:>13}×")
    print(f"  Status:       {s['status']:>14}")
    if s.get("wow"):
        w = s["wow"]
        sign = "+" if w["diff_pct"] >= 0 else ""
        print("-" * 55)
        print(f"  vs last week: {sign}{w['diff_pct']}%  (was {w['prev_pct']}%)")
    print("=" * 55)
    if s["daily_breakdown"]:
        print("  Daily breakdown:")
        for day_iso, toks in sorted(s["daily_breakdown"].items()):
            print(f"    {day_iso}  {toks:>12,}")
    print()


def run(dry_run: bool = False, stats_only: bool = False) -> None:
    print("[tracker] Parsing Claude Code session files…")
    raw = sum_tokens_for_week(week_start_dow=WEEK_START_DOW)
    print(f"[tracker] Scanned {raw['files_scanned']} JSONL files")
    print(f"[tracker] Tokens this week: {raw['total_tokens']:,}")

    stats = build_stats(
        tokens_used=raw["total_tokens"],
        input_tokens=raw["input_tokens"],
        output_tokens=raw["output_tokens"],
        cache_tokens=raw["cache_creation_tokens"],
        week_start=raw["week_start"],
        daily_breakdown=raw["daily_breakdown"],
        detected_limit=raw["detected_limit"],
        week_start_dow=WEEK_START_DOW,
    )

    _print_stats(stats)

    if stats_only:
        return

    if not dry_run:
        init_db()
        save_snapshot(
            tokens_used=stats["tokens_used"],
            input_tokens=stats["input_tokens"],
            output_tokens=stats["output_tokens"],
            cache_tokens=stats["cache_tokens"],
            week_start=stats["week_start"],
            daily_breakdown=stats["daily_breakdown"],
        )
        print("[tracker] Snapshot saved to DB")

        ok = send_daily_report(stats)
        print(f"[tracker] Discord notification: {'sent ✓' if ok else 'failed ✗'}")
    else:
        print("[tracker] --dry-run: skipped DB save and Discord send")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    only = "--stats" in sys.argv
    run(dry_run=dry, stats_only=only)
