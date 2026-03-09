"""Plotext burnup chart with Rich integration."""

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import plotext as plt
from rich.ansi import AnsiDecoder
from rich.console import Console, ConsoleOptions, Group, RenderableType
from rich.jupyter import JupyterMixin

try:
    from ..data.models import BurnMetrics, LimitData, MonthlyLimitData, UsageSnapshot
    from ..utils.formatting import get_utilization_color
except ImportError:
    from ccburn.data.models import BurnMetrics, LimitData, MonthlyLimitData, UsageSnapshot
    from ccburn.utils.formatting import get_utilization_color


class BurnupChart(JupyterMixin):
    """Rich-compatible burnup chart using plotext."""

    def __init__(
        self,
        limit_data: LimitData | MonthlyLimitData | None,
        snapshots: list[UsageSnapshot],
        since_duration: timedelta | None = None,
        until: str = "now",
        explicit_height: int | None = None,
        burn_metrics: BurnMetrics | None = None,
    ):
        """Initialize the burnup chart.

        Args:
            limit_data: Current limit data (for window boundaries)
            snapshots: Historical snapshots to plot
            since_duration: Duration for zoom view (sliding window, e.g., last 1h)
            until: Display end when using since: 'now' or 'end' (window end)
            explicit_height: Override chart height
            burn_metrics: Burn rate metrics for projection line
        """
        self.limit_data = limit_data
        self.snapshots = snapshots
        self.since_duration = since_duration
        self.until = until
        self.explicit_height = explicit_height
        self.burn_metrics = burn_metrics
        self.decoder = AnsiDecoder()

    def _compute_display_window(
        self,
        window_start: datetime,
        window_end: datetime,
        now: datetime,
    ) -> tuple[datetime, datetime]:
        """Compute the visible display window for the chart.

        Returns:
            (display_start, display_end) tuple
        """
        display_start = window_start
        display_end = window_end

        if self.since_duration:
            display_start = max(window_start, now - self.since_duration)

        if self.since_duration and self.until == "now":
            # Sliding window: both edges move forward with time
            display_end = now
        elif self.until == "depleted":
            # Zoom to projected depletion time, fallback to window end
            if self.burn_metrics and self.burn_metrics.percent_per_hour > 0:
                current_pct = self.limit_data.utilization * 100
                if current_pct < 100.0:
                    hours_to_100 = (100.0 - current_pct) / self.burn_metrics.percent_per_hour
                    depletion_time = now + timedelta(hours=hours_to_100)
                    if depletion_time < window_end:
                        # Add 5% padding so the depleted line isn't at the edge
                        visible_hours = (depletion_time - display_start).total_seconds() / 3600
                        padding = timedelta(hours=visible_hours * 0.05)
                        display_end = min(depletion_time + padding, window_end)

        return display_start, display_end

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> Generator[RenderableType, None, None]:
        """Render the plotext chart for Rich console."""
        width = options.max_width or console.width
        height = self.explicit_height or options.height or 15

        chart_str = self._create_chart(width, height)

        # Decode ANSI and render using AnsiDecoder
        rich_canvas = Group(*self.decoder.decode(chart_str))
        yield rich_canvas

    def _create_chart(self, width: int, height: int) -> str:
        """Create the plotext chart.

        Args:
            width: Chart width in characters
            height: Chart height in lines

        Returns:
            Rendered chart as string with ANSI codes
        """
        plt.clear_figure()
        plt.clear_data()
        plt.clear_color()

        # Disable size limiter for larger charts
        plt.limit_size(False, False)

        # Configure plot size - use full available space
        chart_width = max(width, 40)
        chart_height = max(height, 8)
        plt.plotsize(chart_width, chart_height)

        if self.limit_data is None:
            # No data - show empty chart
            plt.title("No data available")
            return plt.build()

        # Determine time window - keep original window for pace calculation
        original_window_start = self.limit_data.window_start
        original_window_hours = self.limit_data.window_hours
        window_end = self.limit_data.resets_at
        now = datetime.now(timezone.utc)

        display_start, display_end = self._compute_display_window(
            original_window_start, window_end, now
        )

        # Filter snapshots to display window
        relevant_snapshots = [
            s for s in self.snapshots
            if display_start <= s.timestamp <= now
        ]

        # Convert timestamps to relative hours from display start
        def to_hours(dt: datetime) -> float:
            return (dt - display_start).total_seconds() / 3600

        display_hours = (display_end - display_start).total_seconds() / 3600

        # Plot budget pace line - shows expected utilization at each point
        # Based on ORIGINAL window, not zoomed view
        num_points = 50
        pace_x = []
        pace_y = []
        for i in range(num_points):
            # X position in display coordinates
            x_hours = i * display_hours / (num_points - 1)
            pace_x.append(x_hours)
            # Calculate actual time at this point
            point_time = display_start + timedelta(hours=x_hours)
            # Budget pace = how far through the ORIGINAL window we are
            elapsed_in_original = (point_time - original_window_start).total_seconds() / 3600
            pace_pct = (elapsed_in_original / original_window_hours) * 100
            pace_y.append(min(pace_pct, 100.0))  # Cap at 100%
        plt.plot(
            pace_x,
            pace_y,
            color=(100, 100, 100),  # Dim gray RGB
            marker="braille",
            label="Budget Pace",
        )

        # Plot actual usage if we have data
        values = []
        if relevant_snapshots:
            times = []

            for s in relevant_snapshots:
                limit = s.get_limit(self.limit_data.limit_type)
                if limit:
                    # Cap utilization to valid range (handles bad historical data)
                    util_pct = min(limit.utilization * 100, 100.0)
                    # Skip obviously bad data (utilization > 1.0 means unnormalized)
                    if limit.utilization > 1.0:
                        continue
                    times.append(to_hours(s.timestamp))
                    values.append(util_pct)

            if times:
                # Calculate budget pace for color determination
                elapsed_hours = (now - original_window_start).total_seconds() / 3600
                budget_pace = min(elapsed_hours / original_window_hours, 1.0)
                # Determine line color based on utilization AND burn rate
                color = self._get_plotext_color(self.limit_data.utilization, budget_pace)
                # Use fillx=True for area chart effect (fills down to x-axis)
                plt.plot(
                    times,
                    values,
                    color=color,
                    marker="braille",
                    fillx=True,
                    label="Usage",
                )

        # Plot projection line if we have positive burn rate and display extends past now
        hits_100_hours = None  # Track when projection hits 100% for vertical marker
        show_projection = display_end > now
        if self.burn_metrics and self.burn_metrics.percent_per_hour > 0 and show_projection:
            current_pct = self.limit_data.utilization * 100
            now_hours = to_hours(now)

            # Only draw projection if not already at or above 100%
            if current_pct < 100.0:
                # Calculate time to hit 100%
                remaining_pct = 100.0 - current_pct
                hours_to_100 = remaining_pct / self.burn_metrics.percent_per_hour

                # End point: either 100% or window end, whichever comes first
                remaining_window_hours = (display_end - now).total_seconds() / 3600

                if hours_to_100 <= remaining_window_hours:
                    # Will hit 100% before window ends
                    end_hours = now_hours + hours_to_100
                    end_pct = 100.0
                    proj_color = (255, 100, 0)  # Orange - warning
                    hits_100_hours = end_hours  # Mark for vertical line
                else:
                    # Won't hit 100%, project to window end
                    end_hours = now_hours + remaining_window_hours
                    end_pct = current_pct + (self.burn_metrics.percent_per_hour * remaining_window_hours)
                    proj_color = (100, 200, 100)  # Green - safe

                plt.plot(
                    [now_hours, end_hours],
                    [current_pct, min(end_pct, 100.0)],
                    color=proj_color,
                    marker="braille",
                    label="Projection",
                )

        # Configure axes
        plt.xlim(0, display_hours)

        # Y-axis: dynamic when zoomed (--since), fixed 0-100 otherwise
        if self.since_duration and values:
            # Calculate dynamic range from data with padding
            all_y_values = values + pace_y
            data_min = min(all_y_values)
            data_max = max(all_y_values)
            # Add 10% padding for readability
            padding = (data_max - data_min) * 0.1
            y_min = max(0, data_min - padding)
            y_max = min(100, data_max + padding)
            # Ensure at least 10% range for visibility
            if y_max - y_min < 10:
                mid = (y_min + y_max) / 2
                y_min = max(0, mid - 5)
                y_max = min(100, mid + 5)
        else:
            y_min, y_max = 0, 100

        plt.ylim(y_min, y_max)

        # Add "now" vertical line when display extends past now
        # Use dotted effect by plotting points at intervals
        now_hours_for_tick = None
        if show_projection:
            now_hours = to_hours(now)
            if 0 < now_hours < display_hours:
                # Create dotted vertical line with points using braille marker to match other lines
                num_dots = 20
                dot_y = [y_min + i * (y_max - y_min) / (num_dots - 1) for i in range(num_dots)]
                dot_x = [now_hours] * num_dots
                plt.plot(dot_x, dot_y, color=(0, 120, 255), marker="braille", label="Now")
                now_hours_for_tick = now_hours

        # Add "hits 100%" vertical line when projection exceeds budget
        hits_100_hours_for_tick = None
        if hits_100_hours is not None and 0 < hits_100_hours < display_hours:
            num_dots = 20
            dot_y = [y_min + i * (y_max - y_min) / (num_dots - 1) for i in range(num_dots)]
            dot_x = [hits_100_hours] * num_dots
            plt.plot(dot_x, dot_y, color=(255, 100, 0), marker="braille", label="Depleted")
            hits_100_hours_for_tick = hits_100_hours

        # Enable right Y axis with same range
        plt.plot([display_hours], [y_max], marker=" ", yside="right")  # Hidden point to enable right axis
        plt.ylim(y_min, y_max, yside="right")

        # Generate x-axis ticks with actual timestamps in local timezone
        num_ticks = 5
        tick_positions = []
        tick_labels = []
        for i in range(num_ticks):
            hours = i * display_hours / (num_ticks - 1)
            tick_positions.append(hours)
            # Convert to actual time in local timezone
            tick_time = display_start + timedelta(hours=hours)
            local_time = tick_time.astimezone()  # Convert to local timezone
            # Round to nearest minute for stable display
            if local_time.second >= 30:
                local_time = local_time.replace(second=0, microsecond=0) + timedelta(minutes=1)
            else:
                local_time = local_time.replace(second=0, microsecond=0)
            # Format based on window size
            if display_hours > 168:  # > 7 days (monthly)
                # Show month/day for multi-week windows (e.g., "2/8" for Feb 8)
                tick_labels.append(f"{local_time.month}/{local_time.day}")
            elif display_hours > 24:
                # Show day and time for multi-day windows (e.g., "Mon 15h")
                tick_labels.append(local_time.strftime("%a %Hh"))
            else:
                # Show just time for short windows (e.g., "15:59")
                tick_labels.append(local_time.strftime("%H:%M"))

        # Add "Now" tick if showing the now line (show actual time)
        # Remove any existing ticks that are too close to avoid overlap/flickering
        if now_hours_for_tick is not None:
            min_distance = display_hours / 10  # Minimum 10% of display width apart
            # Filter out ticks that are too close to "Now"
            filtered = [(pos, label) for pos, label in zip(tick_positions, tick_labels, strict=True)
                        if abs(now_hours_for_tick - pos) >= min_distance]
            tick_positions = [pos for pos, _ in filtered]
            tick_labels = [label for _, label in filtered]
            # Add the "Now" tick
            tick_positions.append(now_hours_for_tick)
            local_now = now.astimezone()
            # Round to nearest minute
            if local_now.second >= 30:
                local_now = local_now.replace(second=0, microsecond=0) + timedelta(minutes=1)
            else:
                local_now = local_now.replace(second=0, microsecond=0)
            if display_hours > 168:
                tick_labels.append(f"{local_now.month}/{local_now.day} {local_now.hour}h")
            elif display_hours > 24:
                tick_labels.append(local_now.strftime("%a %Hh"))
            else:
                tick_labels.append(local_now.strftime("%H:%M"))

        # Add "100%" tick if showing the hits-100 line
        if hits_100_hours_for_tick is not None:
            min_distance = display_hours / 10  # Minimum 10% of display width apart
            # Filter out ticks that are too close to "100%"
            filtered = [(pos, label) for pos, label in zip(tick_positions, tick_labels, strict=True)
                        if abs(hits_100_hours_for_tick - pos) >= min_distance]
            tick_positions = [pos for pos, _ in filtered]
            tick_labels = [label for _, label in filtered]
            # Add the "100%" tick with timestamp
            hits_100_time = display_start + timedelta(hours=hits_100_hours_for_tick)
            local_hits_100 = hits_100_time.astimezone()
            # Round to nearest minute
            if local_hits_100.second >= 30:
                local_hits_100 = local_hits_100.replace(second=0, microsecond=0) + timedelta(minutes=1)
            else:
                local_hits_100 = local_hits_100.replace(second=0, microsecond=0)
            tick_positions.append(hits_100_hours_for_tick)
            if display_hours > 168:
                tick_labels.append(f"{local_hits_100.month}/{local_hits_100.day} {local_hits_100.hour}h")
            elif display_hours > 24:
                tick_labels.append(local_hits_100.strftime("%a %Hh"))
            else:
                tick_labels.append(local_hits_100.strftime("%H:%M"))

        plt.xticks(tick_positions, tick_labels)

        # No labels on axes
        plt.xlabel("")
        plt.ylabel("")

        # Theme and styling
        plt.theme("dark")

        # Use transparent/default background to match terminal
        plt.canvas_color("default")
        plt.axes_color("default")
        plt.ticks_color((100, 100, 100))  # Dim gray for ticks/border

        return plt.build()

    def _get_plotext_color(
        self, utilization: float, budget_pace: float = 0.0
    ) -> tuple[int, int, int]:
        """Get plotext RGB color based on utilization and burn rate.

        Args:
            utilization: Current utilization (0-1)
            budget_pace: How much of window has elapsed (0-1)

        Returns:
            RGB tuple for plotext - bright vivid colors matching Rich progress bars
        """
        # Reuse shared color logic, map Rich color names to RGB
        color_name = get_utilization_color(utilization, budget_pace)
        color_map = {
            "green": (0, 255, 0),
            "yellow": (255, 255, 0),
            "bright_red": (255, 165, 0),  # Orange
            "red": (255, 0, 0),
        }
        return color_map.get(color_name, (255, 255, 0))


def create_simple_chart(
    limit_data: LimitData | MonthlyLimitData | None,
    snapshots: list[UsageSnapshot],
    width: int = 80,
    height: int = 15,
    since_duration: timedelta | None = None,
) -> str:
    """Create a simple chart string without Rich integration.

    Args:
        limit_data: Current limit data
        snapshots: Historical snapshots
        width: Chart width
        height: Chart height
        since_duration: Duration for zoom view (sliding window)

    Returns:
        Rendered chart string
    """
    chart = BurnupChart(limit_data, snapshots, since_duration=since_duration, explicit_height=height)
    return chart._create_chart(width, height)
