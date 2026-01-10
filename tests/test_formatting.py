"""Tests for formatting utilities."""

from datetime import datetime, timedelta, timezone

import pytest

from ccburn.utils.formatting import (
    format_duration,
    format_percentage,
    format_reset_time,
    get_utilization_color,
    get_status_indicator,
)


class TestFormatDuration:
    """Tests for format_duration."""

    def test_minutes_only(self):
        assert format_duration(45) == "45m"
        assert format_duration(1) == "1m"
        assert format_duration(59) == "59m"

    def test_hours_only(self):
        assert format_duration(60) == "1h"
        assert format_duration(120) == "2h"

    def test_hours_and_minutes(self):
        assert format_duration(90) == "1h 30m"
        assert format_duration(134) == "2h 14m"

    def test_days_only(self):
        assert format_duration(24 * 60) == "1d"
        assert format_duration(48 * 60) == "2d"

    def test_days_and_hours(self):
        assert format_duration(25 * 60) == "1d 1h"
        assert format_duration(50 * 60) == "2d 2h"

    def test_negative(self):
        assert format_duration(-10) == "0m"

    def test_zero(self):
        assert format_duration(0) == "0m"


class TestFormatPercentage:
    """Tests for format_percentage."""

    def test_whole_number(self):
        assert format_percentage(0.62) == "62%"
        assert format_percentage(0.5) == "50%"
        assert format_percentage(1.0) == "100%"

    def test_with_decimals(self):
        assert format_percentage(0.625, decimal_places=1) == "62.5%"
        assert format_percentage(0.333, decimal_places=2) == "33.30%"

    def test_zero(self):
        assert format_percentage(0.0) == "0%"


class TestFormatResetTime:
    """Tests for format_reset_time."""

    def test_less_than_24_hours(self):
        now = datetime(2026, 1, 8, 14, 0, 0, tzinfo=timezone.utc)
        resets_at = datetime(2026, 1, 8, 16, 14, 0, tzinfo=timezone.utc)

        result = format_reset_time(resets_at, now)
        assert result == "Resets in 2h 14m"

    def test_less_than_1_hour(self):
        now = datetime(2026, 1, 8, 14, 0, 0, tzinfo=timezone.utc)
        resets_at = datetime(2026, 1, 8, 14, 30, 0, tzinfo=timezone.utc)

        result = format_reset_time(resets_at, now)
        assert result == "Resets in 30m"

    def test_already_reset(self):
        now = datetime(2026, 1, 8, 14, 0, 0, tzinfo=timezone.utc)
        resets_at = datetime(2026, 1, 8, 13, 0, 0, tzinfo=timezone.utc)

        result = format_reset_time(resets_at, now)
        assert result == "Reset pending"


class TestGetUtilizationColor:
    """Tests for get_utilization_color."""

    def test_green(self):
        assert get_utilization_color(0.0) == "green"
        assert get_utilization_color(0.3) == "green"
        assert get_utilization_color(0.49) == "green"

    def test_yellow(self):
        assert get_utilization_color(0.5) == "yellow"
        assert get_utilization_color(0.6) == "yellow"
        assert get_utilization_color(0.74) == "yellow"

    def test_orange(self):
        assert get_utilization_color(0.75) == "bright_red"
        assert get_utilization_color(0.8) == "bright_red"
        assert get_utilization_color(0.89) == "bright_red"

    def test_red(self):
        assert get_utilization_color(0.9) == "red"
        assert get_utilization_color(0.95) == "red"
        assert get_utilization_color(1.0) == "red"


class TestGetStatusIndicator:
    """Tests for get_status_indicator."""

    def test_plenty_available(self):
        assert get_status_indicator(0.3, 0.5) == "[ ]"

    def test_on_track(self):
        assert get_status_indicator(0.6, 0.7) == "[*]"

    def test_above_pace(self):
        assert get_status_indicator(0.7, 0.5) == "[!]"

    def test_caution(self):
        assert get_status_indicator(0.8, 0.9) == "[!]"

    def test_critical(self):
        assert get_status_indicator(0.95, 0.5) == "[X]"
