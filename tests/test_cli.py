"""Tests for CLI commands."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ccburn.cli import parse_duration
from ccburn.main import app

runner = CliRunner()


class TestParseDuration:
    """Tests for parse_duration."""

    def test_minutes(self):
        assert parse_duration("30m") == timedelta(minutes=30)
        assert parse_duration("1m") == timedelta(minutes=1)

    def test_hours(self):
        assert parse_duration("2h") == timedelta(hours=2)
        assert parse_duration("24h") == timedelta(hours=24)

    def test_days(self):
        assert parse_duration("1d") == timedelta(days=1)
        assert parse_duration("7d") == timedelta(days=7)

    def test_weeks(self):
        assert parse_duration("1w") == timedelta(weeks=1)

    def test_case_insensitive(self):
        assert parse_duration("2H") == timedelta(hours=2)
        assert parse_duration("1D") == timedelta(days=1)

    def test_invalid_format(self):
        import typer

        with pytest.raises(typer.BadParameter):
            parse_duration("invalid")

        with pytest.raises(typer.BadParameter):
            parse_duration("2x")

        with pytest.raises(typer.BadParameter):
            parse_duration("abc")


class TestCLI:
    """Tests for CLI commands."""

    def test_version(self):
        import re
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "ccburn" in result.stdout
        # Check for semantic version pattern (e.g., 0.1.7)
        assert re.search(r"\d+\.\d+\.\d+", result.stdout)

    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "session" in result.stdout
        assert "weekly" in result.stdout
        assert "weekly-sonnet" in result.stdout

    def test_session_help(self):
        result = runner.invoke(app, ["session", "--help"])
        assert result.exit_code == 0
        assert "5-hour" in result.stdout

    def test_weekly_help(self):
        result = runner.invoke(app, ["weekly", "--help"])
        assert result.exit_code == 0
        assert "7-day" in result.stdout

    def test_weekly_sonnet_help(self):
        result = runner.invoke(app, ["weekly-sonnet", "--help"])
        assert result.exit_code == 0
        assert "Sonnet" in result.stdout

    def test_clear_history_help(self):
        result = runner.invoke(app, ["clear-history", "--help"])
        assert result.exit_code == 0
        assert "Clear" in result.stdout

    @patch("ccburn.main.auto_detect_limit_type")
    @patch("ccburn.app.CCBurnApp")
    def test_json_output_flag(self, mock_app_class, mock_auto_detect):
        """Test --json flag triggers JSON output mode."""
        from ccburn.data.models import LimitType

        mock_auto_detect.return_value = LimitType.SESSION
        mock_app = MagicMock()
        mock_app.run.return_value = 0
        mock_app_class.return_value = mock_app

        _result = runner.invoke(app, ["--json", "--once"])

        mock_app_class.assert_called_once()
        call_kwargs = mock_app_class.call_args.kwargs
        assert call_kwargs["json_output"] is True
        assert call_kwargs["once"] is True

    @patch("ccburn.main.auto_detect_limit_type")
    @patch("ccburn.app.CCBurnApp")
    def test_compact_output_flag(self, mock_app_class, mock_auto_detect):
        """Test --compact flag triggers compact output mode."""
        from ccburn.data.models import LimitType

        mock_auto_detect.return_value = LimitType.SESSION
        mock_app = MagicMock()
        mock_app.run.return_value = 0
        mock_app_class.return_value = mock_app

        _result = runner.invoke(app, ["--compact"])

        mock_app_class.assert_called_once()
        call_kwargs = mock_app_class.call_args.kwargs
        assert call_kwargs["compact"] is True

    @patch("ccburn.main.auto_detect_limit_type")
    @patch("ccburn.app.CCBurnApp")
    def test_interval_flag(self, mock_app_class, mock_auto_detect):
        """Test --interval flag sets refresh interval."""
        from ccburn.data.models import LimitType

        mock_auto_detect.return_value = LimitType.SESSION
        mock_app = MagicMock()
        mock_app.run.return_value = 0
        mock_app_class.return_value = mock_app

        _result = runner.invoke(app, ["--interval", "60", "--once"])

        mock_app_class.assert_called_once()
        call_kwargs = mock_app_class.call_args.kwargs
        assert call_kwargs["interval"] == 60

    @patch("ccburn.main.auto_detect_limit_type")
    @patch("ccburn.app.CCBurnApp")
    def test_since_flag(self, mock_app_class, mock_auto_detect):
        """Test --since flag sets time window as sliding duration."""
        from datetime import timedelta

        from ccburn.data.models import LimitType

        mock_auto_detect.return_value = LimitType.SESSION
        mock_app = MagicMock()
        mock_app.run.return_value = 0
        mock_app_class.return_value = mock_app

        _result = runner.invoke(app, ["--since", "2h", "--once"])

        mock_app_class.assert_called_once()
        call_kwargs = mock_app_class.call_args.kwargs
        assert call_kwargs["since_duration"] == timedelta(hours=2)  # timedelta for sliding window
