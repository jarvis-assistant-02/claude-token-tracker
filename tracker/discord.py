"""
Build and send the daily token report as a rich Discord embed.
"""
import os
import requests
from datetime import datetime, timezone

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Embed colours
_COL_GREEN  = 0x22D07A
_COL_YELLOW = 0xF5A623
_COL_RED    = 0xFF5470
_COL_PURPLE = 0x7C4DFF
_COL_BLUE   = 0x4F8EF7


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _progress_bar(pct: float, width: int = 24) -> str:
    filled = round(pct / 100 * width)
    filled = max(0, min(filled, width))
    bar = "█" * filled + "░" * (width - filled)
    return f"`{bar}` {pct:.1f}%"


def _status_color(status: str) -> int:
    return {"on_track": _COL_GREEN, "slightly_low": _COL_YELLOW, "under_using": _COL_RED}.get(status, _COL_BLUE)


def _status_label(status: str, multiplier: float) -> str:
    if status == "on_track":
        return "✅  ON TRACK — Keep going, you're crushing it!"
    if status == "slightly_low":
        return f"🟡  SLIGHTLY BEHIND — Use **{multiplier}×** more today to catch up"
    return f"🔴  USE MORE — Only on pace for {100 / multiplier:.0f}% of your budget!\nOpen Claude and work on something NOW."


def _week_bar(day_of_week: int) -> str:
    days = []
    for i in range(1, 8):
        if i < day_of_week:
            days.append("■")
        elif i == day_of_week:
            days.append("▶")
        else:
            days.append("□")
    labels = " ".join(_DAY_NAMES)
    icons  = " ".join(days)
    return f"`{icons}`\n`{labels}`"


def _send(payload: dict) -> bool:
    if not WEBHOOK_URL:
        print("[Discord] DISCORD_WEBHOOK_URL not set — skipping send")
        return False
    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if r.status_code not in (200, 204):
            print(f"[Discord] HTTP {r.status_code}: {r.text[:300]}")
            return False
        return True
    except Exception as e:
        print(f"[Discord] Error: {e}")
        return False


def send_daily_report(stats: dict) -> bool:
    s = stats
    today_str = s["today"].strftime("%A, %d %b %Y")
    week_num  = s["today"].isocalendar()[1]
    color     = _status_color(s["status"])

    # ── Header embed ──────────────────────────────────────────────────────────
    header_embed = {
        "title": f"🤖  Claude Code · Daily Token Report",
        "description": (
            f"**{today_str}** · Week {week_num} · "
            f"Day **{s['day_of_week']}/7**\n\n"
            + _week_bar(s["day_of_week"])
        ),
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {
            "text": f"Budget source: {s['budget_source']} · Claude Token Tracker"
        },
    }

    # ── Progress embed ────────────────────────────────────────────────────────
    budget_note = ""
    if s["budget_source"] in ("default", "observed"):
        budget_note = "\n> ⚠️ Budget is estimated. Set `WEEKLY_TOKEN_BUDGET` in `.env` for accuracy."

    progress_embed = {
        "title": "📊  Weekly Progress",
        "color": color,
        "fields": [
            {
                "name": "Usage bar",
                "value": _progress_bar(s["pct_used"]),
                "inline": False,
            },
            {
                "name": "Tokens used",
                "value": f"**{_fmt_tokens(s['tokens_used'])}** / {_fmt_tokens(s['budget'])}",
                "inline": True,
            },
            {
                "name": "Remaining",
                "value": f"**{_fmt_tokens(s['tokens_remaining'])}**",
                "inline": True,
            },
            {
                "name": "Ideal pace by now",
                "value": f"**{s['ideal_pct_by_now']}%** ({_fmt_tokens(s['ideal_tokens_by_now'])})",
                "inline": True,
            },
        ],
        "description": budget_note or None,
    }
    if not budget_note:
        del progress_embed["description"]

    # ── Projection embed ──────────────────────────────────────────────────────
    proj_icon = "✅" if s["projected_pct"] >= 95 else "🟡" if s["projected_pct"] >= 70 else "🔴"
    projection_embed = {
        "title": "📈  Projection & Daily Target",
        "color": color,
        "fields": [
            {
                "name": "End-of-week forecast",
                "value": (
                    f"{proj_icon} At current pace you'll use **{s['projected_pct']}%** "
                    f"({_fmt_tokens(s['projected_total'])} tokens)"
                ),
                "inline": False,
            },
            {
                "name": "Daily average so far",
                "value": f"**{_fmt_tokens(s['daily_avg'])}** tokens/day",
                "inline": True,
            },
            {
                "name": "Daily target to hit 100%",
                "value": (
                    f"**{_fmt_tokens(s['daily_target'])}** tokens/day"
                    if s["days_remaining"] > 0
                    else "_Last day of week_"
                ),
                "inline": True,
            },
            {
                "name": "Multiplier needed",
                "value": (
                    f"**{s['multiplier']}×** more than today's average"
                    if s["multiplier"] > 1.05
                    else "✅ You're on pace!"
                ),
                "inline": True,
            },
        ],
    }

    # ── Week-over-week embed (only after first week) ──────────────────────────
    wow_embed = None
    if s.get("wow"):
        w = s["wow"]
        arrow = "🟢 ▲" if w["ahead"] else "🔴 ▼"
        diff_sign = "+" if w["diff_pct"] >= 0 else ""
        wow_embed = {
            "title": "📅  vs Last Week (same day)",
            "color": _COL_PURPLE,
            "fields": [
                {
                    "name": "Last week at this point",
                    "value": f"**{w['prev_pct']}%** ({_fmt_tokens(w['prev_tokens'])} tokens)",
                    "inline": True,
                },
                {
                    "name": "This week so far",
                    "value": f"**{s['pct_used']}%** ({_fmt_tokens(s['tokens_used'])} tokens)",
                    "inline": True,
                },
                {
                    "name": "Difference",
                    "value": f"{arrow} **{diff_sign}{w['diff_pct']}%**",
                    "inline": True,
                },
            ],
        }

    # ── Action embed ──────────────────────────────────────────────────────────
    action_embed = {
        "title": "💬  Action",
        "color": color,
        "description": _status_label(s["status"], s["multiplier"]),
    }

    # ── Token breakdown embed ─────────────────────────────────────────────────
    breakdown_lines = []
    for day_iso, toks in sorted(s["daily_breakdown"].items()):
        from datetime import date
        d = date.fromisoformat(day_iso)
        bar_w = 10
        day_pct = toks / s["budget"] * 100 if s["budget"] > 0 else 0
        mini = "█" * round(day_pct / 100 * bar_w) + "░" * (bar_w - round(day_pct / 100 * bar_w))
        breakdown_lines.append(
            f"`{d.strftime('%a %d')}` `{mini}` {_fmt_tokens(toks)} ({day_pct:.1f}%)"
        )

    breakdown_embed = None
    if breakdown_lines:
        breakdown_embed = {
            "title": "📆  Daily Breakdown This Week",
            "color": _COL_BLUE,
            "description": "\n".join(breakdown_lines),
        }

    # Assemble embeds (max 10, Discord limit)
    embeds = [header_embed, progress_embed, projection_embed]
    if wow_embed:
        embeds.append(wow_embed)
    embeds.append(action_embed)
    if breakdown_embed:
        embeds.append(breakdown_embed)

    payload = {
        "username": "Claude Token Tracker",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/4712/4712027.png",
        "embeds": embeds[:10],
    }
    return _send(payload)
