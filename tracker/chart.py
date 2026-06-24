"""
Weekly token usage chart — Style 2A (Monochrome: white ring + iOS blue).
Concentric rings (should-be outer, you-are inner) + daily bar chart.
"""
import io
from datetime import timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Palette
_BG     = "#000000"
_C1     = "#E8E8ED"   # outer ring — should be (soft white)
_C2     = "#0A84FF"   # inner ring — you are (iOS blue)
_BAR    = "#0A84FF"
_MUTED  = "#636366"
_TEXT   = "#F5F5F7"

matplotlib.rcParams["font.family"] = "Helvetica Neue"
matplotlib.rcParams["axes.unicode_minus"] = False


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def _draw_ring(ax, radius: float, pct: float, color: str, lw: float = 13) -> None:
    theta_full = np.linspace(0, 2 * np.pi, 300)
    ax.plot(radius * np.cos(theta_full), radius * np.sin(theta_full),
            color=color, lw=lw, solid_capstyle="round", alpha=0.18, zorder=1)
    if pct > 0:
        sweep = min(pct / 100, 0.9999) * 2 * np.pi
        theta = np.linspace(np.pi / 2, np.pi / 2 - sweep, 300)
        ax.plot(radius * np.cos(theta), radius * np.sin(theta),
                color=color, lw=lw, solid_capstyle="round", zorder=2)


def generate_chart(stats: dict) -> bytes:
    pct       = stats["pct_used"]
    ideal_pct = stats["ideal_pct"]
    grade     = stats["pace_grade"]
    reset_str = stats["reset_in_str"]
    week_num  = stats["today"].isocalendar()[1]
    day_num   = stats["day_of_week"]
    today_idx = day_num - 1
    ideal_daily = stats["ideal_daily"]

    W = stats["week_start_date"]
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    daily_tokens = [
        stats["daily_breakdown"].get((W + timedelta(days=i)).isoformat(), 0)
        for i in range(7)
    ]

    fig = plt.figure(figsize=(8.5, 4.0), facecolor=_BG)
    gs  = fig.add_gridspec(1, 2, width_ratios=[1, 1.65], wspace=0.04,
                           left=0.02, right=0.97, top=0.88, bottom=0.12)
    ax_ring = fig.add_subplot(gs[0])
    ax_bar  = fig.add_subplot(gs[1])

    for ax in (ax_ring, ax_bar):
        ax.set_facecolor(_BG)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.tick_params(colors=_MUTED, labelsize=8.5, length=0)

    # ── Rings ─────────────────────────────────────────────────────────────────
    ax_ring.set_xlim(-1.1, 1.1)
    ax_ring.set_ylim(-1.1, 1.1)
    ax_ring.set_aspect("equal")
    ax_ring.axis("off")

    _draw_ring(ax_ring, 0.78, ideal_pct, _C1, lw=13)
    _draw_ring(ax_ring, 0.52, pct,       _C2, lw=13)

    ax_ring.text(0,  0.12, f"{pct:.1f}%", ha="center", va="center",
                 fontsize=24, fontweight="bold", color=_C2)
    ax_ring.text(0, -0.14, f"of {ideal_pct:.0f}% ideal", ha="center", va="center",
                 fontsize=9, color=_MUTED, fontweight="light")

    for y, col, label in ((-0.82, _C2, "You are"), (-0.96, _C1, "Should be")):
        ax_ring.plot(-0.80, y, "o", color=col, ms=5.5, zorder=3)
        ax_ring.text(-0.66, y, label, va="center", color=_MUTED, fontsize=7.5)

    # ── Bars ──────────────────────────────────────────────────────────────────
    max_val = max(max(daily_tokens), 1)
    y_max   = max_val * 2.6
    x       = np.arange(7)

    bar_cols = []
    for i, t in enumerate(daily_tokens):
        bar_cols.append(_BAR if (i <= today_idx and t > 0) else _MUTED + "22")

    bars = ax_bar.bar(x, daily_tokens, color=bar_cols, width=0.42,
                      zorder=2, linewidth=0)

    if 0 <= today_idx < 7:
        bars[today_idx].set_linewidth(1.3)
        bars[today_idx].set_edgecolor(_TEXT)

    ideal_y = min(ideal_daily, y_max * 0.88)
    ax_bar.axhline(y=ideal_y, color=_C1, ls="--", lw=0.9, alpha=0.5, zorder=3)
    ax_bar.text(6.45, ideal_y + y_max * 0.03, _fmt(int(ideal_daily)),
                ha="right", color=_C1, fontsize=7.5, alpha=0.7)

    for bar, t in zip(bars, daily_tokens):
        if t > 0:
            ax_bar.text(bar.get_x() + bar.get_width() / 2, t + y_max * 0.03,
                        _fmt(t), ha="center", color=_TEXT,
                        fontsize=8, fontweight="bold")

    ax_bar.set_xticks(x)
    ax_bar.set_xticklabels(day_names, color=_MUTED, fontsize=8.5)
    if 0 <= today_idx < 7:
        ax_bar.get_xticklabels()[today_idx].set_color(_TEXT)
        ax_bar.get_xticklabels()[today_idx].set_fontweight("bold")
    ax_bar.yaxis.set_visible(False)
    ax_bar.set_xlim(-0.6, 6.6)
    ax_bar.set_ylim(0, y_max)
    ax_bar.set_facecolor(_BG)

    # ── Title + caption ───────────────────────────────────────────────────────
    fig.text(0.5, 0.96,
             f"Week {week_num}  ·  Day {day_num}/7  ·  Grade {grade}  ·  Resets {reset_str}",
             ha="center", color=_MUTED, fontsize=8.5, fontweight="light")
    fig.text(0.5, 0.01,
             "bars = this device  ·  ring = account-wide",
             ha="center", color=_MUTED, fontsize=6.5, fontweight="light", alpha=0.6)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=155, bbox_inches="tight", facecolor=_BG)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
