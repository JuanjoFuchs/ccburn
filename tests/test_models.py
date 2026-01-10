"""Tests for data models."""

from datetime import timedelta

import pytest

from ccburn.data.models import LimitType, UsageSnapshot


class TestLimitType:
    """Tests for LimitType enum."""

    def test_window_hours(self):
        assert LimitType.SESSION.window_hours == 5
        assert LimitType.WEEKLY.window_hours == 168
        assert LimitType.WEEKLY_SONNET.window_hours == 168

    def test_display_name(self):
        assert LimitType.SESSION.display_name == "Session (5h)"
        assert LimitType.WEEKLY.display_name == "Weekly"
        assert LimitType.WEEKLY_SONNET.display_name == "Weekly Sonnet"

    def test_api_field(self):
        assert LimitType.SESSION.api_field == "five_hour"
        assert LimitType.WEEKLY.api_field == "seven_day"
        assert LimitType.WEEKLY_SONNET.api_field == "seven_day_sonnet"


class TestLimitData:
    """Tests for LimitData dataclass."""

    def test_utilization_percent(self, sample_limit_data):
        assert sample_limit_data.utilization_percent == 62.0

    def test_window_hours(self, sample_limit_data):
        assert sample_limit_data.window_hours == 5

    def test_window_start(self, sample_limit_data):
        expected = sample_limit_data.resets_at - timedelta(hours=5)
        assert sample_limit_data.window_start == expected


class TestUsageSnapshot:
    """Tests for UsageSnapshot dataclass."""

    def test_from_api_response(self, sample_api_response):
        snapshot = UsageSnapshot.from_api_response(sample_api_response)

        # Verify session limit
        assert snapshot.session is not None
        assert snapshot.session.utilization == pytest.approx(0.62, abs=0.001)
        assert snapshot.session.limit_type == LimitType.SESSION

        # Verify weekly limit
        assert snapshot.weekly is not None
        assert snapshot.weekly.utilization == pytest.approx(0.29, abs=0.001)
        assert snapshot.weekly.limit_type == LimitType.WEEKLY

        # Verify sonnet limit
        assert snapshot.weekly_sonnet is not None
        assert snapshot.weekly_sonnet.utilization == pytest.approx(0.01, abs=0.001)
        assert snapshot.weekly_sonnet.limit_type == LimitType.WEEKLY_SONNET

        # Verify opus limit (tracked but not displayed)
        assert snapshot.weekly_opus is not None
        assert snapshot.weekly_opus.utilization == pytest.approx(0.05, abs=0.001)

    def test_get_limit(self, sample_snapshot):
        assert sample_snapshot.get_limit(LimitType.SESSION) == sample_snapshot.session
        assert sample_snapshot.get_limit(LimitType.WEEKLY) == sample_snapshot.weekly
        assert (
            sample_snapshot.get_limit(LimitType.WEEKLY_SONNET)
            == sample_snapshot.weekly_sonnet
        )

    def test_from_api_response_with_missing_data(self):
        """Should handle missing data gracefully."""
        partial_response = {
            "five_hour": {
                "utilization": 50,
                "resets_at": "2026-01-08T16:46:00Z",
            },
            # Missing seven_day, seven_day_sonnet, etc.
        }
        snapshot = UsageSnapshot.from_api_response(partial_response)

        assert snapshot.session is not None
        assert snapshot.weekly is None
        assert snapshot.weekly_sonnet is None
        assert snapshot.weekly_opus is None

    def test_from_api_response_with_null_utilization(self):
        """Should handle null utilization."""
        response = {
            "five_hour": {
                "utilization": None,
                "resets_at": "2026-01-08T16:46:00Z",
            },
        }
        snapshot = UsageSnapshot.from_api_response(response)
        assert snapshot.session is None

    def test_stores_raw_response(self, sample_api_response):
        snapshot = UsageSnapshot.from_api_response(sample_api_response)
        assert snapshot.raw_response is not None
        assert "five_hour" in snapshot.raw_response
