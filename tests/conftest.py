"""Pytest fixtures for ccburn tests."""

from datetime import datetime, timedelta, timezone

import pytest

from ccburn.data.models import LimitData, LimitType, UsageSnapshot


@pytest.fixture
def sample_api_response():
    """Sample API response data."""
    return {
        "five_hour": {
            "utilization": 62,  # 0-100 scale
            "resets_at": "2026-01-08T16:46:00Z",
        },
        "seven_day": {
            "utilization": 29,
            "resets_at": "2026-01-12T00:00:00Z",
        },
        "seven_day_sonnet": {
            "utilization": 1,
            "resets_at": "2026-01-12T00:00:00Z",
        },
        "seven_day_opus": {
            "utilization": 5,
            "resets_at": "2026-01-12T00:00:00Z",
        },
        "extra_usage": {
            "is_enabled": False,
            "utilization": None,
        },
    }


@pytest.fixture
def sample_snapshot(sample_api_response):
    """Sample UsageSnapshot from API response."""
    return UsageSnapshot.from_api_response(
        sample_api_response,
        timestamp=datetime(2026, 1, 8, 14, 32, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_limit_data():
    """Sample LimitData for session."""
    return LimitData(
        utilization=0.62,
        resets_at=datetime(2026, 1, 8, 16, 46, 0, tzinfo=timezone.utc),
        limit_type=LimitType.SESSION,
    )


@pytest.fixture
def sample_snapshots():
    """Sample list of snapshots for burn rate calculation."""
    base_time = datetime(2026, 1, 8, 14, 0, 0, tzinfo=timezone.utc)
    snapshots = []

    # Create 10 snapshots over 5 minutes
    for i in range(10):
        ts = base_time + timedelta(seconds=i * 30)
        utilization = 0.50 + (i * 0.01)  # Increases by 1% every 30 seconds

        snapshot = UsageSnapshot(
            timestamp=ts,
            session=LimitData(
                utilization=utilization,
                resets_at=datetime(2026, 1, 8, 19, 0, 0, tzinfo=timezone.utc),
                limit_type=LimitType.SESSION,
            ),
            weekly=None,
            weekly_sonnet=None,
            weekly_opus=None,
        )
        snapshots.append(snapshot)

    return snapshots


@pytest.fixture
def temp_db(tmp_path):
    """Temporary database path."""
    return tmp_path / "test_history.db"
