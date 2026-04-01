"""Fast statusline collector — standalone entry point.

Reads Claude Code statusline JSON from stdin, extracts rate_limits,
saves to SQLite history DB, and passes stdin through to stdout.

This bypasses Typer/Rich for minimal startup latency (~50ms vs ~500ms).
Used as: ccburn-collect (separate entry point in pyproject.toml)
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    five_hour_utilization REAL,
    five_hour_resets_at TEXT,
    seven_day_all_utilization REAL,
    seven_day_all_resets_at TEXT,
    seven_day_sonnet_utilization REAL,
    seven_day_sonnet_resets_at TEXT,
    seven_day_opus_utilization REAL,
    seven_day_opus_resets_at TEXT,
    monthly_limit_cents INTEGER,
    monthly_used_credits_cents REAL,
    monthly_utilization REAL,
    monthly_resets_at TEXT,
    raw_response TEXT
);
CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON usage_snapshots(timestamp);
"""


def _get_data_dir() -> Path:
    """Get ccburn data dir, respecting CLAUDE_CONFIG_DIR for multi-profile."""
    claude_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if claude_dir:
        claude_path = Path(claude_dir).expanduser()
        suffix = claude_path.name.removeprefix(".claude")
        return claude_path.parent / f".ccburn{suffix}"
    return Path.home() / ".ccburn"


def _normalize_resets_at(val) -> str:
    """Convert resets_at from epoch int or ISO string to ISO string."""
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=timezone.utc).isoformat()
    return val or ""


def main():
    raw = sys.stdin.buffer.read()

    # Pass through immediately
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()

    try:
        data = json.loads(raw)
        rate_limits = data.get("rate_limits")
        if not rate_limits:
            return

        # Parse rate_limits into DB columns
        now = datetime.now(timezone.utc).isoformat()

        def get_field(key):
            block = rate_limits.get(key)
            if block and isinstance(block, dict):
                return (
                    (block.get("used_percentage", 0) or 0) / 100.0,
                    _normalize_resets_at(block.get("resets_at")),
                )
            return None, None

        fh_util, fh_resets = get_field("five_hour")
        sd_util, sd_resets = get_field("seven_day")
        ss_util, ss_resets = get_field("seven_day_sonnet")
        so_util, so_resets = get_field("seven_day_opus")

        # Monthly from extra_usage if present
        extra = rate_limits.get("extra_usage")
        m_limit = m_used = m_util = m_resets = None
        if extra and isinstance(extra, dict) and extra.get("is_enabled"):
            m_limit = extra.get("monthly_limit")
            m_used = extra.get("used_credits")
            m_util_raw = extra.get("utilization")
            m_util = (m_util_raw / 100.0) if m_util_raw is not None else None
            # Compute resets_at as 1st of next month
            n = datetime.now(timezone.utc)
            if n.month == 12:
                m_resets = datetime(n.year + 1, 1, 1, tzinfo=timezone.utc).isoformat()
            else:
                m_resets = datetime(n.year, n.month + 1, 1, tzinfo=timezone.utc).isoformat()

        # Write to DB
        data_dir = _get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = data_dir / "history.db"

        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.executescript(SCHEMA)
        conn.execute(
            """INSERT INTO usage_snapshots (
                timestamp,
                five_hour_utilization, five_hour_resets_at,
                seven_day_all_utilization, seven_day_all_resets_at,
                seven_day_sonnet_utilization, seven_day_sonnet_resets_at,
                seven_day_opus_utilization, seven_day_opus_resets_at,
                monthly_limit_cents, monthly_used_credits_cents,
                monthly_utilization, monthly_resets_at,
                raw_response
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                now,
                fh_util, fh_resets,
                sd_util, sd_resets,
                ss_util, ss_resets,
                so_util, so_resets,
                m_limit, m_used, m_util, m_resets,
                json.dumps(rate_limits),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # Never break the statusline pipeline


if __name__ == "__main__":
    main()
