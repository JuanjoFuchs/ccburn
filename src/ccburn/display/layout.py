"""Layout manager for ccburn TUI."""

import os
from datetime import datetime, timezone

from rich.console import Console
from rich.layout import Layout
from rich.text import Text

try:
    from ..data.models import LimitData, LimitType, UsageSnapshot, BurnMetrics
    from ..utils.calculator import calculate_budget_pace, calculate_burn_metrics
    from .gauges import create_header, create_gauge_section
    from .chart import BurnupChart
except ImportError:
    from ccburn.data.models import LimitData, LimitType, UsageSnapshot, BurnMetrics
    from ccburn.utils.calculator import calculate_budget_pace, calculate_burn_metrics
    from ccburn.display.gauges import create_header, create_gauge_section
    from ccburn.display.chart import BurnupChart


class BurnupLayout:
    """Layout manager for the ccburn TUI."""

    MIN_WIDTH = 40
    MIN_HEIGHT = 10
    COMPACT_WIDTH = 60
    COMPACT_HEIGHT = 15

    def __init__(self, console: Console | None = None):
        """Initialize the layout manager.

        Args:
            console: Rich Console instance (creates one if not provided)
        """
        self.console = console or Console()
        self._last_limit_data: LimitData | None = None
        self._last_snapshots: list[UsageSnapshot] = []
        self._last_metrics: BurnMetrics | None = None
        self._error_message: str | None = None
        self._stale_data_time: datetime | None = None

    def get_terminal_size(self) -> tuple[int, int]:
        """Get current terminal size.

        Returns:
            (width, height) tuple
        """
        try:
            size = os.get_terminal_size()
            return size.columns, size.lines
        except OSError:
            return 80, 24  # Default fallback

    def should_use_compact_mode(self) -> bool:
        """Determine if compact mode should be used.

        Returns:
            True if terminal is too small for full layout
        """
        width, height = self.get_terminal_size()
        return width < self.COMPACT_WIDTH or height < self.COMPACT_HEIGHT

    def update(
        self,
        limit_type: LimitType,
        limit_data: LimitData | None,
        snapshots: list[UsageSnapshot],
        error: str | None = None,
        stale_since: datetime | None = None,
        since: datetime | None = None,
    ) -> Layout:
        """Update the layout with new data.

        Args:
            limit_type: Which limit to display
            limit_data: Current limit data
            snapshots: Historical snapshots for chart
            error: Error message to display (if any)
            stale_since: When data became stale (if using cached data)
            since: Zoom view start time

        Returns:
            Updated Rich Layout
        """
        self._last_limit_data = limit_data
        self._last_snapshots = snapshots
        self._error_message = error
        self._stale_data_time = stale_since

        # Calculate metrics
        if limit_data:
            self._last_metrics = calculate_burn_metrics(limit_data, snapshots)

        width, height = self.get_terminal_size()

        if self.should_use_compact_mode():
            return self._create_compact_layout(limit_type, width, height)

        return self._create_full_layout(limit_type, width, height, since)

    def _create_full_layout(
        self,
        limit_type: LimitType,
        width: int,
        height: int,
        since: datetime | None = None,
    ) -> Layout:
        """Create full TUI layout with header, gauges, and chart.

        Args:
            limit_type: Which limit to display
            width: Terminal width
            height: Terminal height
            since: Zoom view start time

        Returns:
            Rich Layout
        """
        root = Layout()

        # Calculate sizes - minimize header/gauges, maximize chart
        header_height = 1
        gauges_height = 2  # Two progress bars
        error_height = 1 if self._error_message or self._stale_data_time else 0
        # Use full remaining height for chart (no extra padding with screen=True)
        chart_height = height - header_height - gauges_height - error_height

        # Create sections
        header_layout = Layout(size=header_height, name="header")
        gauges_layout = Layout(size=gauges_height, name="gauges")
        chart_layout = Layout(name="chart")

        # Add error banner if needed
        if self._error_message or self._stale_data_time:
            error_layout = Layout(size=error_height, name="error")
            root.split_column(header_layout, gauges_layout, error_layout, chart_layout)
            error_layout.update(self._create_error_banner())
        else:
            root.split_column(header_layout, gauges_layout, chart_layout)

        # Update header
        header_layout.update(create_header(limit_type, self._last_limit_data))

        # Update gauges
        budget_pace = 0.0
        if self._last_limit_data:
            budget_pace = calculate_budget_pace(
                self._last_limit_data.resets_at,
                self._last_limit_data.window_hours,
            )
        gauges_layout.update(create_gauge_section(self._last_limit_data, budget_pace))

        # Update chart
        chart = BurnupChart(
            self._last_limit_data,
            self._last_snapshots,
            since=since,
            explicit_height=chart_height,
        )
        chart_layout.update(chart)

        return root

    def _create_compact_layout(
        self,
        limit_type: LimitType,
        width: int,
        height: int,
    ) -> Layout:
        """Create compact layout for small terminals.

        Args:
            limit_type: Which limit to display
            width: Terminal width
            height: Terminal height

        Returns:
            Rich Layout with minimal display
        """
        root = Layout()

        # Just header and gauges in compact mode
        header_layout = Layout(size=1, name="header")
        gauges_layout = Layout(size=3, name="gauges")
        info_layout = Layout(name="info")

        root.split_column(header_layout, gauges_layout, info_layout)

        # Update header
        header_layout.update(create_header(limit_type, self._last_limit_data))

        # Update gauges
        budget_pace = 0.0
        if self._last_limit_data:
            budget_pace = calculate_budget_pace(
                self._last_limit_data.resets_at,
                self._last_limit_data.window_hours,
            )
        gauges_layout.update(create_gauge_section(self._last_limit_data, budget_pace))

        # Show info text instead of chart
        info_text = Text("Terminal too small for chart. Expand window or use --compact.", style="dim")
        if self._error_message:
            info_text = Text(self._error_message, style="yellow")
        info_layout.update(info_text)

        return root

    def _create_error_banner(self) -> Text:
        """Create error/warning banner.

        Returns:
            Rich Text with error/warning message
        """
        if self._error_message:
            return Text(f"Warning: {self._error_message}", style="yellow")

        if self._stale_data_time:
            from ..utils.formatting import format_duration

            now = datetime.now(timezone.utc)
            minutes_stale = int((now - self._stale_data_time).total_seconds() / 60)
            return Text(
                f"Using cached data (last updated {format_duration(minutes_stale)} ago)",
                style="yellow",
            )

        return Text("")

    def render(self) -> Layout:
        """Get the current layout without updating data.

        Returns:
            Current Rich Layout
        """
        limit_type = LimitType.SESSION
        if self._last_limit_data:
            limit_type = self._last_limit_data.limit_type

        width, height = self.get_terminal_size()

        if self.should_use_compact_mode():
            return self._create_compact_layout(limit_type, width, height)

        return self._create_full_layout(limit_type, width, height)
