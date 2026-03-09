"""Tests for chart display window logic."""

from datetime import datetime, timedelta, timezone

from ccburn.data.models import BurnMetrics, LimitData, LimitType
from ccburn.display.chart import BurnupChart


def _make_chart(
    utilization=0.5,
    hours_left=4.0,
    percent_per_hour=20.0,
    since_duration=None,
    until="now",
):
    """Create a BurnupChart with controllable parameters."""
    now = datetime.now(timezone.utc)
    limit = LimitData(
        utilization=utilization,
        resets_at=now + timedelta(hours=hours_left),
        limit_type=LimitType.SESSION,
    )
    metrics = BurnMetrics(
        limit_type=LimitType.SESSION,
        percent_per_hour=percent_per_hour,
        trend="high",
        estimated_minutes_to_100=150,
        budget_pace=0.5,
        status="ahead_of_pace",
        recommendation="conserve",
    ) if percent_per_hour > 0 else None

    return BurnupChart(
        limit_data=limit,
        snapshots=[],
        since_duration=since_duration,
        until=until,
        burn_metrics=metrics,
    )


class TestComputeDisplayWindow:
    """Tests for _compute_display_window — the core display range logic."""

    def test_depleted_crops_before_window_end(self):
        """until='depleted' should crop display_end when depletion is before window end.

        50% used at 20%/hr → depletes in 2.5h. Window ends in 4h.
        display_end should be around 2.5h + 5% padding, NOT 4h.
        """
        chart = _make_chart(utilization=0.5, hours_left=4.0, percent_per_hour=20.0, until="depleted")
        now = datetime.now(timezone.utc)
        window_start = chart.limit_data.window_start
        window_end = chart.limit_data.resets_at

        _start, display_end = chart._compute_display_window(window_start, window_end, now)

        # display_end should be well before window_end (depletion at ~2.5h, window at 4h)
        assert display_end < window_end
        hours_shown = (display_end - now).total_seconds() / 3600
        assert 2.4 < hours_shown < 3.0  # ~2.5h + padding

    def test_depleted_without_since_duration(self):
        """--since start --until depleted: depleted logic must work with since_duration=None.

        This is the regression test for the bug where depleted was gated on since_duration.
        """
        chart = _make_chart(
            utilization=0.5, hours_left=4.0, percent_per_hour=20.0,
            since_duration=None, until="depleted",
        )
        now = datetime.now(timezone.utc)
        window_start = chart.limit_data.window_start
        window_end = chart.limit_data.resets_at

        _start, display_end = chart._compute_display_window(window_start, window_end, now)

        assert display_end < window_end, "depleted should crop even without since_duration"

    def test_depleted_with_since_duration(self):
        """--since 2h --until depleted: depleted works with a since_duration too."""
        chart = _make_chart(
            utilization=0.5, hours_left=4.0, percent_per_hour=20.0,
            since_duration=timedelta(hours=2), until="depleted",
        )
        now = datetime.now(timezone.utc)
        window_start = chart.limit_data.window_start
        window_end = chart.limit_data.resets_at

        _start, display_end = chart._compute_display_window(window_start, window_end, now)

        assert display_end < window_end

    def test_depleted_falls_back_to_window_end_when_under_budget(self):
        """If depletion projects past window end, display_end should be window_end."""
        # 10% used at 5%/hr → depletes in 18h. Window ends in 4h.
        chart = _make_chart(
            utilization=0.1, hours_left=4.0, percent_per_hour=5.0, until="depleted",
        )
        now = datetime.now(timezone.utc)
        window_start = chart.limit_data.window_start
        window_end = chart.limit_data.resets_at

        _start, display_end = chart._compute_display_window(window_start, window_end, now)

        assert display_end == window_end

    def test_since_duration_now_is_sliding_window(self):
        """--since 2h (default --until now) should end at now, not window_end."""
        chart = _make_chart(since_duration=timedelta(hours=2), until="now")
        now = datetime.now(timezone.utc)
        window_start = chart.limit_data.window_start
        window_end = chart.limit_data.resets_at

        _start, display_end = chart._compute_display_window(window_start, window_end, now)

        assert display_end == now

    def test_since_start_until_end_shows_full_window(self):
        """--since start --until end should show from window_start to window_end."""
        chart = _make_chart(since_duration=None, until="end")
        now = datetime.now(timezone.utc)
        window_start = chart.limit_data.window_start
        window_end = chart.limit_data.resets_at

        display_start, display_end = chart._compute_display_window(window_start, window_end, now)

        assert display_start == window_start
        assert display_end == window_end

    def test_no_burn_metrics_depleted_falls_back(self):
        """until='depleted' without burn metrics should fall back to window_end."""
        chart = _make_chart(
            utilization=0.5, hours_left=4.0, percent_per_hour=0, until="depleted",
        )
        now = datetime.now(timezone.utc)
        window_start = chart.limit_data.window_start
        window_end = chart.limit_data.resets_at

        _start, display_end = chart._compute_display_window(window_start, window_end, now)

        assert display_end == window_end
