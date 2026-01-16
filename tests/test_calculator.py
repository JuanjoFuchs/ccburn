"""Tests for calculator utilities."""

from datetime import datetime, timedelta, timezone

import pytest

from ccburn.data.models import LimitData, LimitType, UsageSnapshot
from ccburn.utils.calculator import (
    calculate_budget_pace,
    calculate_burn_metrics,
    calculate_burn_rate,
    classify_burn_trend,
    estimate_time_to_empty,
    get_recommendation,
    get_status,
)


class TestCalculateBudgetPace:
    """Tests for calculate_budget_pace."""

    def test_at_window_start(self):
        """Budget pace should be 0 at window start."""
        now = datetime.now(timezone.utc)
        resets_at = now + timedelta(hours=5)  # Full window ahead

        pace = calculate_budget_pace(resets_at, 5)
        assert pace == pytest.approx(0.0, abs=0.01)

    def test_at_window_end(self):
        """Budget pace should be 1 at window end."""
        now = datetime.now(timezone.utc)
        resets_at = now  # At the reset point

        pace = calculate_budget_pace(resets_at, 5)
        assert pace == pytest.approx(1.0, abs=0.01)

    def test_at_window_middle(self):
        """Budget pace should be 0.5 at window middle."""
        now = datetime.now(timezone.utc)
        resets_at = now + timedelta(hours=2.5)  # Half window ahead

        pace = calculate_budget_pace(resets_at, 5)
        assert pace == pytest.approx(0.5, abs=0.01)

    def test_clamped_to_bounds(self):
        """Budget pace should be clamped between 0 and 1."""
        now = datetime.now(timezone.utc)

        # Past the reset time
        resets_at = now - timedelta(hours=1)
        pace = calculate_budget_pace(resets_at, 5)
        assert pace == 1.0

        # Way before window start
        resets_at = now + timedelta(hours=10)
        pace = calculate_budget_pace(resets_at, 5)
        assert pace == pytest.approx(0.0, abs=0.01)


class TestCalculateBurnRate:
    """Tests for calculate_burn_rate."""

    def test_no_snapshots(self):
        """Burn rate should be 0 with no snapshots."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=5)
        rate = calculate_burn_rate([], LimitType.SESSION, window_start, window_hours=5)
        assert rate == 0.0

    def test_one_snapshot(self):
        """Burn rate should be 0 with only one snapshot."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=3)
        snapshot = UsageSnapshot(
            timestamp=now,
            session=LimitData(
                utilization=0.5,
                resets_at=now + timedelta(hours=2),
                limit_type=LimitType.SESSION,
            ),
            weekly=None,
            weekly_sonnet=None,
            weekly_opus=None,
        )
        rate = calculate_burn_rate([snapshot], LimitType.SESSION, window_start, window_hours=5)
        assert rate == 0.0

    def test_increasing_usage(self, sample_snapshots):
        """Burn rate should be positive when usage is increasing."""
        # sample_snapshots are from 2026-01-08 14:00:00 to 14:04:30 (4.5 min span)
        # Window starts before the first snapshot
        # Use 30-minute window so 4.5 min span > 10% minimum (3 min)
        window_start = datetime(2026, 1, 8, 13, 55, 0, tzinfo=timezone.utc)
        rate = calculate_burn_rate(
            sample_snapshots, LimitType.SESSION, window_start, window_hours=0.5
        )
        # With 10% increase over 4.5 minutes, rate should be ~133%/hour
        assert rate > 0

    def test_constant_usage(self):
        """Burn rate should be 0 when usage is constant."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=1)
        snapshots = []
        for i in range(5):
            ts = now - timedelta(minutes=i)
            snapshot = UsageSnapshot(
                timestamp=ts,
                session=LimitData(
                    utilization=0.5,  # Constant
                    resets_at=now + timedelta(hours=2),
                    limit_type=LimitType.SESSION,
                ),
                weekly=None,
                weekly_sonnet=None,
                weekly_opus=None,
            )
            snapshots.append(snapshot)

        snapshots.sort(key=lambda s: s.timestamp)
        rate = calculate_burn_rate(snapshots, LimitType.SESSION, window_start, window_hours=5)
        assert rate == pytest.approx(0.0, abs=0.1)


class TestEstimateTimeToEmpty:
    """Tests for estimate_time_to_empty."""

    def test_positive_burn_rate(self):
        """Should return valid estimate with positive burn rate."""
        # At 50% utilization, burning 10%/hour -> 50% remaining / 10%/hour = 5 hours = 300 minutes
        minutes = estimate_time_to_empty(0.5, 10)
        assert minutes == 300

    def test_zero_burn_rate(self):
        """Should return None with zero burn rate."""
        minutes = estimate_time_to_empty(0.5, 0)
        assert minutes is None

    def test_negative_burn_rate(self):
        """Should return None with negative burn rate."""
        minutes = estimate_time_to_empty(0.5, -5)
        assert minutes is None

    def test_already_at_100(self):
        """Should return 0 when already at 100%."""
        minutes = estimate_time_to_empty(1.0, 10)
        assert minutes == 0


class TestClassifyBurnTrend:
    """Tests for classify_burn_trend."""

    def test_low(self):
        assert classify_burn_trend(3) == "low"
        assert classify_burn_trend(0) == "low"

    def test_moderate(self):
        assert classify_burn_trend(10) == "moderate"
        assert classify_burn_trend(5) == "moderate"

    def test_high(self):
        assert classify_burn_trend(20) == "high"
        assert classify_burn_trend(15) == "high"

    def test_critical(self):
        assert classify_burn_trend(50) == "critical"
        assert classify_burn_trend(30) == "critical"


class TestGetRecommendation:
    """Tests for get_recommendation."""

    def test_plenty_available(self):
        assert get_recommendation(0.3, 0.5) == "plenty_available"
        assert get_recommendation(0.1, 0.9) == "plenty_available"

    def test_on_track(self):
        assert get_recommendation(0.6, 0.7) == "on_track"

    def test_moderate_pace(self):
        assert get_recommendation(0.7, 0.5) == "moderate_pace"

    def test_conserve(self):
        assert get_recommendation(0.8, 0.5) == "conserve"
        assert get_recommendation(0.85, 0.9) == "conserve"

    def test_critical(self):
        assert get_recommendation(0.95, 0.5) == "critical"


class TestGetStatus:
    """Tests for get_status."""

    def test_on_pace(self):
        assert get_status(0.5, 0.52) == "on_pace"
        assert get_status(0.5, 0.48) == "on_pace"

    def test_ahead_of_pace(self):
        assert get_status(0.7, 0.5) == "ahead_of_pace"

    def test_behind_pace(self):
        assert get_status(0.3, 0.5) == "behind_pace"


class TestCalculateBurnMetrics:
    """Tests for calculate_burn_metrics."""

    def test_returns_all_fields(self, sample_limit_data, sample_snapshots):
        metrics = calculate_burn_metrics(sample_limit_data, sample_snapshots)

        assert metrics.limit_type == LimitType.SESSION
        assert isinstance(metrics.percent_per_hour, float)
        assert metrics.trend in ["low", "moderate", "high", "critical"]
        assert metrics.estimated_minutes_to_100 is None or isinstance(
            metrics.estimated_minutes_to_100, int
        )
        assert 0 <= metrics.budget_pace <= 1
        assert metrics.status in ["ahead_of_pace", "on_pace", "behind_pace"]
        assert metrics.recommendation in [
            "plenty_available",
            "on_track",
            "moderate_pace",
            "conserve",
            "critical",
        ]
