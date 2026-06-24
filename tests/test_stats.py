"""Tests for stat derivation logic."""
from datetime import date, datetime, timezone, timedelta

import pytest

from tracker.stats import _pace_grade, _reset_countdown, build_stats


# ── _pace_grade ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("score,expected", [
    (100.0, "A"),
    (90.0,  "A"),
    (89.9,  "B"),
    (75.0,  "B"),
    (74.9,  "C"),
    (50.0,  "C"),
    (49.9,  "D"),
    (25.0,  "D"),
    (24.9,  "F"),
    (0.0,   "F"),
])
def test_pace_grade_thresholds(score, expected):
    assert _pace_grade(score) == expected


# ── _reset_countdown ──────────────────────────────────────────────────────────

def test_reset_countdown_days_and_hours():
    # Add extra seconds so 1–2s of execution time doesn't flip the hour
    future = datetime.now(timezone.utc) + timedelta(days=3, hours=5, seconds=30)
    result = _reset_countdown(future)
    assert result == "3d 5h"


def test_reset_countdown_hours_only():
    future = datetime.now(timezone.utc) + timedelta(hours=2, minutes=30, seconds=30)
    result = _reset_countdown(future)
    assert result == "2h 30m"


def test_reset_countdown_minutes_only():
    future = datetime.now(timezone.utc) + timedelta(minutes=45, seconds=30)
    result = _reset_countdown(future)
    assert result == "45m"


def test_reset_countdown_past_returns_now():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    assert _reset_countdown(past) == "now"


# ── build_stats ───────────────────────────────────────────────────────────────

def _make_stats(**overrides):
    """Build stats with sensible defaults, overridable per test."""
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=2)
    week_end = now + timedelta(days=5)
    defaults = dict(
        tokens_used=1_000_000,
        input_tokens=700_000,
        output_tokens=300_000,
        cache_tokens=0,
        week_start=week_start,
        week_end=week_end,
        daily_breakdown={},
        detected_limit=None,
    )
    defaults.update(overrides)
    return build_stats(**defaults)


def test_build_stats_pct_used_matches_tokens_and_budget():
    s = _make_stats(tokens_used=500_000)
    assert s["pct_used"] == pytest.approx(s["tokens_used"] / s["budget"] * 100, abs=0.2)


def test_build_stats_tokens_remaining_is_budget_minus_used():
    s = _make_stats(tokens_used=2_000_000)
    assert s["tokens_remaining"] == s["budget"] - s["tokens_used"]


def test_build_stats_day_of_week_is_positive():
    s = _make_stats()
    assert 1 <= s["day_of_week"] <= 7


def test_build_stats_projected_pct_uses_daily_avg():
    s = _make_stats(tokens_used=3_500_000)
    expected_avg = s["tokens_used"] / s["days_elapsed"]
    expected_proj = expected_avg * 7 / s["budget"] * 100
    assert s["projected_pct"] == pytest.approx(expected_proj, abs=1.0)


def test_build_stats_grade_f_when_no_usage():
    s = _make_stats(tokens_used=0)
    assert s["pace_grade"] == "F"


def test_build_stats_grade_a_when_well_ahead():
    # Use nearly all budget on day 3 of 7
    s = _make_stats(tokens_used=45_000_000)
    assert s["pace_grade"] == "A"


def test_build_stats_status_on_track_when_high_projection():
    s = _make_stats(tokens_used=45_000_000)
    assert s["status"] == "on_track"


def test_build_stats_status_under_using_when_low_projection():
    s = _make_stats(tokens_used=100_000)
    assert s["status"] == "under_using"


def test_build_stats_reset_in_str_is_string():
    s = _make_stats()
    assert isinstance(s["reset_in_str"], str)
    assert len(s["reset_in_str"]) > 0


def test_build_stats_api_usage_overrides_pct():
    api = {
        "utilization_7d": 0.42,
        "reset_7d": None,
        "status_7d": "allowed",
        "utilization_5h": None,
        "reset_5h": None,
    }
    s = _make_stats(tokens_used=100_000, api_usage=api)
    assert s["pct_used"] == pytest.approx(42.0, abs=0.1)


def test_build_stats_api_usage_updates_week_end():
    future = datetime.now(timezone.utc) + timedelta(days=4)
    api = {
        "utilization_7d": 0.30,
        "reset_7d": future,
        "status_7d": "allowed",
        "utilization_5h": None,
        "reset_5h": None,
    }
    s = _make_stats(tokens_used=1_000_000, api_usage=api)
    assert s["week_end"] == future


def test_build_stats_wow_is_none_without_history():
    s = _make_stats()
    # No DB snapshot for last week → wow should be None
    assert s["wow"] is None


def test_build_stats_human_convos_non_negative():
    s = _make_stats(tokens_used=49_000_000)   # nearly at budget
    assert s["human_convos"] >= 0
