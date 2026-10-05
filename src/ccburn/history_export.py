"""`ccburn history --json`: print the snapshot history as JSON.

Standalone and stdlib-only, like `collect.py`, so a tool that polls it (once a
minute, say) pays no Typer/Rich startup. Read-only: the database is opened
with `mode=ro` and never created.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

VERSION = 1

# (column prefix, key in the status line's rate_limits)
LIMITS = [
    ("five_hour", "five_hour"),
    ("seven_day_all", "seven_day"),
    ("seven_day_sonnet", "seven_day_sonnet"),
    ("seven_day_opus", "seven_day_opus"),
]


def _get_data_dir() -> Path:
    """Get ccburn data dir, respecting CLAUDE_CONFIG_DIR for multi-profile."""
    claude_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if claude_dir:
        claude_path = Path(claude_dir).expanduser()
        suffix = claude_path.name.removeprefix(".claude")
        return claude_path.parent / f".ccburn{suffix}"
    return Path.home() / ".ccburn"


def _parse_args(argv: list[str]) -> tuple[float, bool]:
    """Return (--since-hours, default 168; --changes-only)."""
    since_hours = 168.0
    changes_only = False
    for i, arg in enumerate(argv):
        if arg == "--since-hours" and i + 1 < len(argv):
            since_hours = float(argv[i + 1])
        elif arg.startswith("--since-hours="):
            since_hours = float(arg.split("=", 1)[1])
        elif arg == "--changes-only":
            changes_only = True
    return since_hours, changes_only


def _parse_time(value: str) -> datetime | None:
    """Stored timestamps mix UTC and local offsets; naive ones are UTC."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def read_snapshots(db_path: Path, since: datetime, changes_only: bool = False) -> list[dict]:
    """Snapshots at or after `since`, oldest first, in the status line's units.

    With `changes_only`, a snapshot whose limits equal the previous one's is
    dropped, except the newest, so the current reading is always present.
    """
    if not db_path.exists():
        return []

    columns = ", ".join(f"{c}_utilization, {c}_resets_at" for c, _ in LIMITS)
    conn = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True, timeout=5)
    try:
        # Timestamps are compared as times, not strings: their offsets differ.
        # The string bound only narrows the scan, a day wider than any offset.
        rows = conn.execute(
            f"SELECT timestamp, {columns} FROM usage_snapshots WHERE timestamp >= ?",
            ((since - timedelta(days=1)).date().isoformat(),),
        ).fetchall()
    finally:
        conn.close()

    timed = []
    for row in rows:
        at = _parse_time(row[0])
        if at is None or at < since:
            continue
        limits = {}
        for i, (_, key) in enumerate(LIMITS):
            utilization, resets_at = row[1 + i * 2], row[2 + i * 2]
            if utilization is None or not resets_at:
                continue
            limits[key] = {"used_percentage": round(utilization * 100, 4), "resets_at": resets_at}
        if limits:
            timed.append((at, {"timestamp": at.astimezone(timezone.utc).isoformat(), "limits": limits}))

    timed.sort(key=lambda pair: pair[0])
    snapshots = [snapshot for _, snapshot in timed]
    if not changes_only:
        return snapshots

    kept = []
    for i, snapshot in enumerate(snapshots):
        is_last = i == len(snapshots) - 1
        if not kept or is_last or snapshot["limits"] != kept[-1]["limits"]:
            kept.append(snapshot)
    return kept


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[2:] if argv is None else argv
    try:
        since_hours, changes_only = _parse_args(argv)
    except ValueError:
        sys.stderr.write("Error: --since-hours takes a number of hours.\n")
        return 2

    data_dir = _get_data_dir()
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    output = {
        "version": VERSION,
        "data_dir": str(data_dir),
        "snapshots": read_snapshots(data_dir / "history.db", since, changes_only),
    }
    sys.stdout.write(json.dumps(output) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
