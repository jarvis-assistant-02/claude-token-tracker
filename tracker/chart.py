"""
Generate the weekly token usage chart as PNG bytes.
Dark Discord-themed matplotlib figure with:
  - Dual horizontal progress bars (used vs ideal pace)
  - Daily vertical bar chart (Mon–Sun) with ideal-daily reference line
"""
import io
from datetime import date, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# Discord dark palette
_BG       = "#313338"
_PLOT_BG  = "#2b2d31"
_TEXT     = "#f2f3f5"
_MUTED    = "#80848e"
_GREEN    = "#23a55a"
_RED      = "#f23f42"
_YELLOW   = "#f0b232"
_BLURPLE  = "#5865f2"
_FUTURE   = "#3c3d44"
_GRID     = "#383a40"


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def generate_chart(stats: dict) -> bytes:
    fig = plt.figure(figsize=(8.5, 4.2), facecolor=_BG)

    # Layout: top strip = dual bars, bottom = daily chart
    gs = fig.add_gridspec(
        2, 1,
        height_ratios=[1, 2.4],
        hspace=0.55,
        left=0.01, right=0.99,
        top=0.88, bottom=0.13,
    )
    ax_top = fig.add_subplot(gs[0])
    ax_bot = fig.add_subplot(gs[1])

    for ax in (ax_top, ax_bot):
        ax.set_facecolor(_PLOT_BG)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(colors=_MUTED, labelsize=8, length=0)

    pct_used  = stats["pct_used"]
    ideal_pct = stats["ideal_pct"]

    # ── TOP: dual horizontal progress bars ───────────────────────────────────
    bh = 0.28  # bar height
    pad = 0.08

    # Tracks (grey background)
    ax_top.barh([1, 0], [100, 100], height=bh, color=_FUTURE, left=0, zorder=1)

    # Ideal bar
    ax_top.barh(1, ideal_pct, height=bh, color=_YELLOW, left=0, zorder=2)

    # Used bar — green if ahead of ideal, red if behind
    used_color = _GREEN if pct_used >= ideal_pct * 0.9 else _RED
    ax_top.barh(0, pct_used, height=bh, color=used_color, left=0, zorder=2)

    # Vertical cursor at current % to make the gap obvious
    ax_top.axvline(x=pct_used, ymin=0.05, ymax=0.95, color=used_color,
                   linewidth=1.5, linestyle="--", zorder=3, alpha=0.7)

    # Value labels inside / outside bars
    for y, pct, color in ((0, pct_used, _TEXT), (1, ideal_pct, _TEXT)):
        x_label = min(pct + 1.5, 97)
        ax_top.text(x_label, y, f"{pct:.1f}%",
                    va="center", ha="left", color=color,
                    fontsize=9, fontweight="bold")

    ax_top.set_xlim(0, 100)
    ax_top.set_ylim(-0.4, 1.55)
    ax_top.set_yticks([0, 1])
    ax_top.set_yticklabels(["  Used", "  Ideal"], color=_MUTED, fontsize=8.5)
    ax_top.xaxis.set_visible(False)

    # ── BOTTOM: daily bar chart ───────────────────────────────────────────────
    day_names   = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    week_start  = stats["week_start_date"]
    today_idx   = stats["day_of_week"] - 1   # 0-based
    ideal_daily = stats["ideal_daily"]

    daily_tokens = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        daily_tokens.append(stats["daily_breakdown"].get(d.isoformat(), 0))

    x = np.arange(7)
    bar_colors = []
    for i, t in enumerate(daily_tokens):
        if i > today_idx:
            bar_colors.append(_FUTURE)
        elif t >= ideal_daily:
            bar_colors.append(_GREEN)
        elif t > 0:
            bar_colors.append(_RED)
        else:
            bar_colors.append(_FUTURE)

    bars = ax_bot.bar(x, daily_tokens, color=bar_colors, width=0.55,
                      zorder=2, edgecolor="none")

    # Highlight today's bar with a bright border
    if 0 <= today_idx < 7:
        bars[today_idx].set_edgecolor(_TEXT)
        bars[today_idx].set_linewidth(1.5)

    # Ideal daily reference line
    if ideal_daily > 0:
        ax_bot.axhline(y=ideal_daily, color=_YELLOW, linestyle="--",
                       linewidth=1.2, zorder=3, alpha=0.85)
        ax_bot.text(6.48, ideal_daily, f"ideal\n{_fmt(int(ideal_daily))}",
                    ha="right", va="bottom", color=_YELLOW,
                    fontsize=7, alpha=0.9)

    # Value labels above non-zero bars
    max_val = max(daily_tokens) if any(daily_tokens) else 1
    for i, (bar, t) in enumerate(zip(bars, daily_tokens)):
        if t > 0:
            ax_bot.text(
                bar.get_x() + bar.get_width() / 2,
                t + max_val * 0.02,
                _fmt(t),
                ha="center", va="bottom",
                color=_TEXT, fontsize=7.5, fontweight="bold",
            )

    ax_bot.set_xticks(x)
    ax_bot.set_xticklabels(day_names, color=_MUTED, fontsize=9)
    ax_bot.yaxis.set_visible(False)
    ax_bot.set_xlim(-0.5, 6.5)
    ax_bot.set_ylim(0, max(max_val * 1.25, ideal_daily * 1.5, 1))
    ax_bot.grid(axis="y", color=_GRID, linewidth=0.6, zorder=0)

    # Mark today's day name
    if 0 <= today_idx < 7:
        ax_bot.get_xticklabels()[today_idx].set_color(_TEXT)
        ax_bot.get_xticklabels()[today_idx].set_fontweight("bold")

    # ── Figure title ──────────────────────────────────────────────────────────
    grade      = stats["pace_grade"]
    reset_str  = stats["reset_in_str"]
    week_num   = stats["today"].isocalendar()[1]
    pace_score = stats["pace_score_pct"]
    streak     = stats["streak"]

    streak_txt = f"  ·  🔥 {streak}d streak" if streak > 0 else ""
    title = (
        f"Week {week_num}  ·  Grade {grade}  ({pace_score:.0f}% of ideal pace)"
        f"  ·  Resets in {reset_str}{streak_txt}"
    )
    fig.text(0.5, 0.95, title, ha="center", va="top",
             color=_MUTED, fontsize=9)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=140, bbox_inches="tight",
                facecolor=_BG, edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
