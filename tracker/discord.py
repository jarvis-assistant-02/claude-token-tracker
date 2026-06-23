"""
Build and send the daily token report as two Discord embeds + a chart image.
Uses multipart/form-data to attach the PNG directly so it renders inline.
"""
import json
import os
from datetime import datetime, timezone

import requests

from tracker.chart import generate_chart

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Sidebar colours
_GREEN   = 0x23A55A
_YELLOW  = 0xF0B232
_RED     = 0xF23F42
_MUTED   = 0x4E5058


def _status_color(status: str) -> int:
    return {"on_track": _GREEN, "slightly_low": _YELLOW, "under_using": _RED}.get(status, _MUTED)


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _dual_bar(pct_used: float, ideal_pct: float, width: int = 22) -> str:
    def bar(pct: float) -> str:
        filled = max(0, min(round(pct / 100 * width), width))
        return "█" * filled + "░" * (width - filled)

    return (
        f"`Used  {bar(pct_used)}`  **{pct_used:.1f}%**\n"
        f"`Ideal {bar(ideal_pct)}`  {ideal_pct:.1f}%"
    )


def _action_text(stats: dict) -> str:
    s = stats["status"]
    grade = stats["pace_grade"]
    proj = stats["projected_pct"]
    dr = stats["days_remaining"]

    if s == "on_track":
        return f"✅  **Grade {grade} — Keep it up!** You're on pace to use {proj:.0f}% this week."

    behind = stats["ideal_pct"] - stats["pct_used"]
    target = _fmt(stats["daily_target"])

    if s == "slightly_low":
        return (
            f"🟡  **Grade {grade} — Slightly behind.** "
            f"You're {behind:.1f} pts below ideal pace.\n"
            f"Need **{target} tokens/day** for the remaining {dr} day{'s' if dr != 1 else ''} to hit 100%."
        )

    return (
        f"🔴  **Grade {grade} — Use more Claude!** "
        f"On track for only **{proj:.0f}%** this week.\n"
        f"Target: **{target} tokens/day** over the next {dr} day{'s' if dr != 1 else ''}. "
        f"Open a project, ask Claude to review your code, build something."
    )


def _send_with_image(embeds: list[dict], image_bytes: bytes) -> bool:
    if not WEBHOOK_URL:
        print("[Discord] DISCORD_WEBHOOK_URL not set — skipping")
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
    s = stats
    color      = _status_color(s["status"])
    today_str  = s["today"].strftime("%a %d %b %Y")
    week_num   = s["today"].isocalendar()[1]
    now_ts     = datetime.now(timezone.utc).isoformat()

    # ── Embed 1: Dashboard ────────────────────────────────────────────────────
    grade_emoji = {"A": "🥇", "B": "🥈", "C": "🥉", "D": "😬", "F": "💀"}.get(s["pace_grade"], "❓")

    # wow line
    wow_line = ""
    if s.get("wow"):
        w = s["wow"]
        arrow = "▲" if w["ahead"] else "▼"
        sign  = "+" if w["diff_pct"] >= 0 else ""
        wow_line = (
            f"\n**vs last week:** {sign}{w['diff_pct']:.1f}%  "
            f"({arrow} was {w['prev_pct']:.1f}% at this point)"
        )

    # streak line
    streak_line = ""
    if s["streak"] > 0:
        streak_line = f"\n🔥  **{s['streak']}-day streak** above ideal pace!"

    # human context
    convo_line = (
        f"\n💬  {_fmt(s['tokens_remaining'])} tokens left "
        f"≈ **{s['human_convos']} long conversations** worth"
    ) if s["human_convos"] > 0 else ""

    # budget caveat
    budget_note = ""
    if s["budget_source"] in ("default", "observed"):
        budget_note = "\n> ⚠️  Budget is estimated — set `WEEKLY_TOKEN_BUDGET` in `.env` for accuracy."

    description = (
        f"{_dual_bar(s['pct_used'], s['ideal_pct'])}\n\n"
        f"📦  **{_fmt(s['tokens_used'])}** / {_fmt(s['budget'])} tokens"
        f"   ·   {grade_emoji} **Grade {s['pace_grade']}** ({s['pace_score_pct']:.0f}% of pace)"
        f"   ·   ⏰ Resets in **{s['reset_in_str']}**\n"
        f"📈  Forecast end-of-week: **{s['projected_pct']:.0f}%**   ·   "
        f"Daily target: **{_fmt(s['daily_target'])}** / day"
        + wow_line
        + streak_line
        + convo_line
        + budget_note
    )

    embed1 = {
        "title":       f"🤖  Claude Tokens  ·  {today_str}  ·  Week {week_num}  ·  Day {s['day_of_week']}/7",
        "description": description,
        "color":       color,
        "timestamp":   now_ts,
        "footer":      {
            "text": f"Pro plan · budget source: {s['budget_source']} · Claude Token Tracker"
        },
    }

    # ── Embed 2: Action + chart ───────────────────────────────────────────────
    embed2 = {
        "description": _action_text(s),
        "color":       color,
        "image":       {"url": "attachment://chart.png"},
    }

    # Generate chart
    try:
        chart_bytes = generate_chart(s)
    except Exception as e:
        print(f"[Chart] Failed to generate: {e}")
        chart_bytes = None

    if chart_bytes:
        return _send_with_image([embed1, embed2], chart_bytes)

    # Fallback: send without image
    try:
        r = requests.post(
            WEBHOOK_URL,
            json={"embeds": [embed1, embed2], "username": "Claude Token Tracker"},
            timeout=15,
        )
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"[Discord] Fallback send error: {e}")
        return False
