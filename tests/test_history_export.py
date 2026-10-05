"""Tests for `ccburn history --json` (specs/004-history-json.md)."""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest


def run(args: list[str], config_dir, stdin: str | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(config_dir), "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "-m", "ccburn.main", *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def collect(config_dir, five: float | None, seven: float | None) -> None:
    rate_limits = {}
    if five is not None:
        rate_limits["five_hour"] = {"used_percentage": five, "resets_at": 1791248400}
    if seven is not None:
        rate_limits["seven_day"] = {"used_percentage": seven, "resets_at": 1791763200}
    result = run(["collect"], config_dir, json.dumps({"rate_limits": rate_limits}))
    assert result.returncode == 0


@pytest.fixture
def profile(tmp_path):
    return tmp_path / ".claude-test"


def test_reads_collected_snapshots_oldest_first(profile):
    collect(profile, 6, 5)
    collect(profile, 7, 5)
    collect(profile, 8, 6)

    result = run(["history", "--json"], profile)
    assert result.returncode == 0
    out = json.loads(result.stdout)

    assert out["version"] == 1
    assert out["data_dir"].endswith(".ccburn-test")
    assert [s["limits"]["five_hour"]["used_percentage"] for s in out["snapshots"]] == [6, 7, 8]
    assert out["snapshots"][-1]["limits"]["seven_day"]["used_percentage"] == 6
    timestamps = [s["timestamp"] for s in out["snapshots"]]
    assert timestamps == sorted(timestamps)


def test_since_hours_drops_old_snapshots(profile):
    import sqlite3

    collect(profile, 6, 5)
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    db = profile.parent / ".ccburn-test" / "history.db"
    conn = sqlite3.connect(db)
    conn.execute("UPDATE usage_snapshots SET timestamp = ?", (old,))
    conn.commit()
    conn.close()
    collect(profile, 9, 5)

    out = json.loads(run(["history", "--json", "--since-hours", "1"], profile).stdout)
    assert [s["limits"]["five_hour"]["used_percentage"] for s in out["snapshots"]] == [9]


def test_no_database_prints_empty_and_creates_nothing(profile):
    result = run(["history", "--json"], profile)
    assert result.returncode == 0
    assert json.loads(result.stdout)["snapshots"] == []
    assert not (profile.parent / ".ccburn-test").exists()


def test_absent_limits_are_omitted(profile):
    collect(profile, 6, None)
    snapshot = json.loads(run(["history", "--json"], profile).stdout)["snapshots"][0]
    assert set(snapshot["limits"]) == {"five_hour"}


def test_changes_only_keeps_changes_and_the_newest(profile):
    for five in (6, 6, 7, 7, 7):
        collect(profile, five, 5)
    out = json.loads(run(["history", "--json", "--changes-only"], profile).stdout)
    assert [s["limits"]["five_hour"]["used_percentage"] for s in out["snapshots"]] == [6, 7, 7]


def test_local_offset_timestamps_are_compared_as_times_and_returned_as_utc(profile):
    import sqlite3

    collect(profile, 6, 5)
    local = datetime.now(timezone(timedelta(hours=-4))).isoformat()
    db = profile.parent / ".ccburn-test" / "history.db"
    conn = sqlite3.connect(db)
    conn.execute("UPDATE usage_snapshots SET timestamp = ?", (local,))
    conn.commit()
    conn.close()

    out = json.loads(run(["history", "--json", "--since-hours", "1"], profile).stdout)
    assert len(out["snapshots"]) == 1
    assert out["snapshots"][0]["timestamp"].endswith("+00:00")


def test_help_and_describe_list_history():
    from typer.testing import CliRunner

    from ccburn.main import app

    runner = CliRunner()
    assert "history" in runner.invoke(app, ["--help"]).output
    assert "ccburn history --json" in runner.invoke(app, ["describe"]).output
