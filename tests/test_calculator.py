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


class TestRecentWindowBurnRate:
    """Tests for calculate_burn_rate with recent_window_minutes."""

    def _make_snapshot(self, ts: datetime, utilization: float) -> UsageSnapshot:
        return UsageSnapshot(
            timestamp=ts,
            session=LimitData(
                utilization=utilization,
                resets_at=ts + timedelta(hours=4),
                limit_type=LimitType.SESSION,
            ),
            weekly=None,
            weekly_sonnet=None,
            weekly_opus=None,
        )

    def test_excludes_old_snapshots(self):
        """recent_window_minutes should ignore snapshots older than the cutoff."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=5)

        # 10 idle snapshots 2h ago (flat at 20%)
        old_snapshots = [
            self._make_snapshot(now - timedelta(hours=2, minutes=i), 0.20)
            for i in range(10)
        ]
        # 5 active snapshots in the last 20 minutes (rising from 20% to 30%)
        recent_snapshots = [
            self._make_snapshot(now - timedelta(minutes=20 - i * 4), 0.20 + i * 0.02)
            for i in range(5)
        ]
        all_snapshots = sorted(old_snapshots + recent_snapshots, key=lambda s: s.timestamp)

        rate_full = calculate_burn_rate(
            all_snapshots, LimitType.SESSION, window_start, window_hours=5
        )
        rate_recent = calculate_burn_rate(
            all_snapshots, LimitType.SESSION, window_start, window_hours=5,
            recent_window_minutes=30,
        )

        # Recent window sees the active slope; full window is diluted by idle data
        assert rate_recent > rate_full

    def test_insufficient_points_returns_zero(self):
        """When fewer than min_points snapshots fall in the recent window, return 0."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=5)

        # 8 snapshots from 2h ago, only 2 in the last 10 minutes
        old_snapshots = [
            self._make_snapshot(now - timedelta(hours=2, minutes=i), 0.20 + i * 0.01)
            for i in range(8)
        ]
        recent_snapshots = [
            self._make_snapshot(now - timedelta(minutes=j * 3), 0.50 + j * 0.02)
            for j in range(2)
        ]
        snapshots = sorted(old_snapshots + recent_snapshots, key=lambda s: s.timestamp)

        rate = calculate_burn_rate(
            snapshots, LimitType.SESSION, window_start, window_hours=5,
            recent_window_minutes=10,
        )
        assert rate == 0.0

    def test_none_is_backward_compatible(self):
        """recent_window_minutes=None must give the same result as not passing the param."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=5)
        snapshots = [
            self._make_snapshot(now - timedelta(minutes=30 - i * 6), 0.10 + i * 0.02)
            for i in range(5)
        ]

        rate_default = calculate_burn_rate(
            snapshots, LimitType.SESSION, window_start, window_hours=5
        )
        rate_none = calculate_burn_rate(
            snapshots, LimitType.SESSION, window_start, window_hours=5,
            recent_window_minutes=None,
        )
        assert rate_default == pytest.approx(rate_none)

    def test_span_check_uses_recent_window_size(self):
        """min_span check should be relative to recent_window_minutes, not the full window."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=5)

        # 4 snapshots spanning 4 minutes — well under 10% of a 5h window (30 min)
        # but comfortably over 10% of a 60m recent window (6 min... wait, 4 < 6)
        # Use a 30m recent window: min_span = 30m * 10% = 3 min, span = 4 min → should pass
        snapshots = [
            self._make_snapshot(now - timedelta(minutes=4 - i), 0.30 + i * 0.03)
            for i in range(4)
        ]

        rate_full = calculate_burn_rate(
            snapshots, LimitType.SESSION, window_start, window_hours=5
        )
        rate_recent = calculate_burn_rate(
            snapshots, LimitType.SESSION, window_start, window_hours=5,
            recent_window_minutes=30,
        )

        # Full window: span (4 min) < min_span (30 min) → 0
        assert rate_full == 0.0
        # Recent window: span (4 min) > min_span (3 min) → non-zero
        assert rate_recent > 0.0


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
