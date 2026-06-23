"""
SQLite storage for daily token snapshots and budget tracking.
DB lives at data/tracker.db relative to the project root.
"""
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "tracker.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS daily_snapshots (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT    NOT NULL,          -- ISO date: 2026-06-23
                week_start    TEXT    NOT NULL,          -- ISO date of Monday
                tokens_used   INTEGER NOT NULL,
                input_tokens  INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cache_tokens  INTEGER NOT NULL DEFAULT 0,
                daily_breakdown TEXT  NOT NULL DEFAULT '{}',
                created_at    TEXT    NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS ux_daily_snapshots_date
                ON daily_snapshots (snapshot_date);

            CREATE TABLE IF NOT EXISTS budget_config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)


def save_snapshot(
    tokens_used: int,
    input_tokens: int,
    output_tokens: int,
    cache_tokens: int,
    week_start: datetime,
    daily_breakdown: dict,
) -> None:
    init_db()
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO daily_snapshots
                (snapshot_date, week_start, tokens_used, input_tokens, output_tokens,
                 cache_tokens, daily_breakdown, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                tokens_used     = excluded.tokens_used,
                input_tokens    = excluded.input_tokens,
                output_tokens   = excluded.output_tokens,
                cache_tokens    = excluded.cache_tokens,
                daily_breakdown = excluded.daily_breakdown,
                created_at      = excluded.created_at
            """,
            (today, week_start.date().isoformat(), tokens_used,
             input_tokens, output_tokens, cache_tokens,
             json.dumps(daily_breakdown), now),
        )


def get_snapshot(snapshot_date: str) -> dict | None:
    init_db()
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM daily_snapshots WHERE snapshot_date = ?", (snapshot_date,)
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["daily_breakdown"] = json.loads(d["daily_breakdown"])
    return d


def get_last_n_weeks_snapshots(n: int = 2) -> list[dict]:
    """Return daily snapshots for the last n weeks, oldest first."""
    init_db()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM daily_snapshots ORDER BY snapshot_date DESC LIMIT ?",
            (n * 7,),
        ).fetchall()
    result = []
    for r in reversed(rows):
        d = dict(r)
        d["daily_breakdown"] = json.loads(d["daily_breakdown"])
        result.append(d)
    return result


def get_peak_weekly_tokens() -> int:
    """Return the highest total tokens seen in any single week."""
    init_db()
    with _conn() as con:
        row = con.execute(
            "SELECT week_start, MAX(tokens_used) as peak FROM daily_snapshots GROUP BY week_start ORDER BY peak DESC LIMIT 1"
        ).fetchone()
    return row["peak"] if row and row["peak"] else 0


def set_budget(key: str, value: str) -> None:
    init_db()
    with _conn() as con:
        con.execute(
            "INSERT INTO budget_config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_budget(key: str, default: str | None = None) -> str | None:
    init_db()
    with _conn() as con:
        row = con.execute("SELECT value FROM budget_config WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def get_same_day_last_week(today_iso: str) -> dict | None:
    """Return the snapshot from exactly 7 days ago."""
    from datetime import timedelta
    d = date.fromisoformat(today_iso) - timedelta(days=7)
    return get_snapshot(d.isoformat())
