"""
Build and send the daily token report — Style B (military brief) + 2A chart.
Two embeds: stat card + chart image sent as multipart attachment.
"""
import json
import os
from datetime import datetime, timezone

import requests

from tracker.chart import generate_chart

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

_GREEN  = 0x0A84FF   # iOS blue — used as the "on" color
_YELLOW = 0xF0B232
_RED    = 0xFF3B30
_DARK   = 0x111111


def _status_color(status: str) -> int:
    return {"on_track": 0x23A55A, "slightly_low": _YELLOW, "under_using": _RED}.get(status, _DARK)


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _grade_label(grade: str) -> str:
    return {"A": "A  — crushing it", "B": "B  — good pace",
            "C": "C  — below pace", "D": "D  — well behind",
            "F": "F  — not using it"}.get(grade, grade)


def _send(embeds: list[dict], image_bytes: bytes) -> bool:
    if not WEBHOOK_URL:
        print("[Discord] DISCORD_WEBHOOK_URL not set")
        return False
    try:
        payload = {"embeds": embeds, "username": "Claude Token Tracker"}
        r = requests.post(
            WEBHOOK_URL,
            data={"payload_json": json.dumps(payload)},
            files={"file": ("chart.png", image_bytes, "image/png")},
            timeout=15,
        )
        if r.status_code not in (200, 204):
            print(f"[Discord] HTTP {r.status_code}: {r.text[:300]}")
            return False
        return True
    except Exception as e:
        print(f"[Discord] Error: {e}")
        return False


def send_daily_report(stats: dict) -> bool:
    s      = stats
    color  = _status_color(s["status"])
    day    = s["today"].strftime("%a %d %b")
    week   = s["today"].isocalendar()[1]
    dr     = s["days_remaining"]

    # wow line
    wow_line = ""
    if s.get("wow"):
        w    = s["wow"]
        sign = "+" if w["diff_pct"] >= 0 else ""
        dir_ = "ahead" if w["ahead"] else "behind"
        wow_line = f"\nVS LAST WK   {sign}{w['diff_pct']:.1f} pts  ({dir_} of same day)"

    # streak line
    streak_line = ""
    if s["streak"] > 0:
        streak_line = f"\nSTREAK       {s['streak']} day{'s' if s['streak'] != 1 else ''} above pace"

    description = (
        f"```\n"
        f"DAY {s['day_of_week']}/7   WEEK {week}   {day}\n"
        f"\n"
        f"STATUS       {_grade_label(s['pace_grade'])}\n"
        f"USED         {_fmt(s['tokens_used'])} / {_fmt(s['budget'])}   ({s['pct_used']:.1f}%)\n"
        f"SHOULD BE    {s['ideal_pct']:.1f}%   (gap: {round(s['ideal_pct'] - s['pct_used'], 1)} pts)\n"
        f"TARGET       {_fmt(s['daily_target'])} tokens today\n"
        f"RESETS       Monday in {s['reset_in_str']}\n"
        f"FORECAST     {s['projected_pct']:.0f}% end of week"
        + wow_line
        + streak_line
        + "\n```"
    )

    embed1 = {
        "description": description,
        "color":       color,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "footer":      {"text": f"Pro plan · {s['budget_source']} budget · Claude Token Tracker"},
    }

    embed2 = {
        "color": color,
        "image": {"url": "attachment://chart.png"},
    }

    try:
        chart_bytes = generate_chart(s)
    except Exception as e:
        print(f"[Chart] Failed: {e}")
        chart_bytes = None

    if chart_bytes:
        return _send([embed1, embed2], chart_bytes)

    # fallback: text only
    try:
        r = requests.post(WEBHOOK_URL,
            json={"embeds": [embed1], "username": "Claude Token Tracker"}, timeout=15)
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"[Discord] Fallback error: {e}")
        return False
