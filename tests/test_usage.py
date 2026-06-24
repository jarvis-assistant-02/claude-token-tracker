"""Tests for JSONL parsing and week-bounds calculation."""
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from tracker.usage import _week_bounds, _tokens_from_entry, sum_tokens_for_week


# ── _week_bounds ──────────────────────────────────────────────────────────────

def test_week_bounds_returns_utc_aware():
    start, end = _week_bounds()
    assert start.tzinfo is not None
    assert end.tzinfo is not None


def test_week_bounds_span_seven_days():
    start, end = _week_bounds()
    assert (end - start).days == 7


def test_week_bounds_start_before_end():
    start, end = _week_bounds()
    assert start < end


def test_week_bounds_now_is_inside_window():
    start, end = _week_bounds()
    now = datetime.now(timezone.utc)
    assert start <= now < end


def test_week_bounds_custom_reset_hour():
    # With reset hour 9, the window should still span 7 days
    start, end = _week_bounds(week_start_dow=0, week_reset_hour=9)
    assert (end - start).days == 7


# ── _tokens_from_entry ────────────────────────────────────────────────────────

def test_tokens_from_entry_sums_correctly():
    entry = {"message": {"usage": {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_creation_input_tokens": 200,
        "cache_read_input_tokens": 999,   # excluded intentionally
    }}}
    assert _tokens_from_entry(entry) == 350


def test_tokens_from_entry_missing_usage():
    assert _tokens_from_entry({}) == 0
    assert _tokens_from_entry({"message": {}}) == 0


def test_tokens_from_entry_partial_fields():
    entry = {"message": {"usage": {"output_tokens": 42}}}
    assert _tokens_from_entry(entry) == 42


def test_tokens_from_entry_non_dict_message():
    assert _tokens_from_entry({"message": "text"}) == 0


# ── sum_tokens_for_week ───────────────────────────────────────────────────────

def _make_entry(ts: datetime, input_t=100, output_t=50, cache_t=0) -> str:
    return json.dumps({
        "timestamp": ts.isoformat(),
        "message": {"usage": {
            "input_tokens": input_t,
            "output_tokens": output_t,
            "cache_creation_input_tokens": cache_t,
            "cache_read_input_tokens": 0,
        }},
    })


def test_sum_tokens_counts_entries_within_week():
    now_utc = datetime.now(timezone.utc)
    start = now_utc - timedelta(days=1)
    end = now_utc + timedelta(days=6)

    entry_inside = _make_entry(now_utc, input_t=100, output_t=50)
    entry_before = _make_entry(start - timedelta(hours=1), input_t=999, output_t=999)

    with tempfile.TemporaryDirectory() as tmpdir:
        proj = Path(tmpdir) / "proj1"
        proj.mkdir()
        (proj / "session.jsonl").write_text(entry_inside + "\n" + entry_before + "\n")

        with patch("tracker.usage.CLAUDE_DIR", Path(tmpdir)):
            result = sum_tokens_for_week(week_start=start, week_end=end)

    assert result["total_tokens"] == 150
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 50


def test_sum_tokens_excludes_cache_read():
    now_utc = datetime.now(timezone.utc)
    start = now_utc - timedelta(hours=1)
    end = now_utc + timedelta(days=6)

    entry = json.dumps({
        "timestamp": now_utc.isoformat(),
        "message": {"usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_creation_input_tokens": 20,
            "cache_read_input_tokens": 1000,  # must not be counted
        }},
    })

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "s.jsonl").write_text(entry + "\n")
        with patch("tracker.usage.CLAUDE_DIR", Path(tmpdir)):
            result = sum_tokens_for_week(week_start=start, week_end=end)

    assert result["total_tokens"] == 35   # 10+5+20, not 1035


def test_sum_tokens_empty_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("tracker.usage.CLAUDE_DIR", Path(tmpdir)):
            result = sum_tokens_for_week()
    assert result["total_tokens"] == 0
    assert result["files_scanned"] == 0


def test_sum_tokens_malformed_lines_ignored():
    now_utc = datetime.now(timezone.utc)
    start = now_utc - timedelta(hours=1)
    end = now_utc + timedelta(days=6)

    good = _make_entry(now_utc, input_t=10, output_t=5)

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "s.jsonl").write_text(
            "not json\n" + "{broken:\n" + good + "\n"
        )
        with patch("tracker.usage.CLAUDE_DIR", Path(tmpdir)):
            result = sum_tokens_for_week(week_start=start, week_end=end)

    assert result["total_tokens"] == 15


def test_sum_tokens_daily_breakdown_groups_by_local_date():
    now_utc = datetime.now(timezone.utc)
    start = now_utc - timedelta(days=2)
    end = now_utc + timedelta(days=5)

    e1 = _make_entry(now_utc - timedelta(days=1), input_t=100, output_t=0)
    e2 = _make_entry(now_utc, input_t=200, output_t=0)

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "s.jsonl").write_text(e1 + "\n" + e2 + "\n")
        with patch("tracker.usage.CLAUDE_DIR", Path(tmpdir)):
            result = sum_tokens_for_week(week_start=start, week_end=end)

    assert result["total_tokens"] == 300
    assert len(result["daily_breakdown"]) >= 1
