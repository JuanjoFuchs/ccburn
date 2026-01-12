"""Progress bar gauges for ccburn TUI."""

from rich.progress import ProgressBar
from rich.style import Style
from rich.table import Table
from rich.text import Text

try:
    from ..data.models import LimitData, LimitType
    from ..utils.calculator import calculate_budget_pace
    from ..utils.formatting import format_reset_time, get_utilization_color
except ImportError:
    from ccburn.data.models import LimitData, LimitType
    from ccburn.utils.calculator import calculate_budget_pace
    from ccburn.utils.formatting import format_reset_time, get_utilization_color


def get_pace_emoji(utilization: float, budget_pace: float) -> str:
    """Get emoji indicator based on utilization vs budget pace.

    Args:
        utilization: Current utilization (0-1)
        budget_pace: Expected budget pace (0-1)

    Returns:
        Emoji: 🧊 (behind), 🔥 (on pace), 🚨 (ahead)
    """
    if budget_pace == 0:
        return "🔥"

    ratio = utilization / budget_pace
    if ratio < 0.85:
        return "🧊"  # Behind pace - ice cold, under budget
    elif ratio > 1.15:
        return "🚨"  # Ahead of pace - alarm!
    else:
        return "🔥"  # On pace - normal burn


def create_header(limit_type: LimitType, limit_data: LimitData | None) -> Table:
    """Create the header line with limit name and reset countdown.

    Args:
        limit_type: Which limit is being displayed
        limit_data: Current limit data (for reset time)

    Returns:
        Rich Table formatted as a single header line
    """
    table = Table.grid(padding=0, expand=True)
    table.add_column(justify="left", ratio=1)
    table.add_column(justify="right", ratio=1)

    # Dynamic pace emoji: 🧊 (behind), 🔥 (on pace), 🚨 (ahead)
    if limit_data:
        pace = calculate_budget_pace(limit_data.resets_at, limit_data.window_hours)
        pace_emoji = get_pace_emoji(limit_data.utilization, pace)
    else:
        pace_emoji = "🔥"  # Default while loading

    title = Text()
    title.append(f"{pace_emoji} ", style="")
    title.append("ccburn", style="bold magenta")
    title.append(" - ", style="dim")
    title.append(limit_type.display_name, style="bold cyan")

    if limit_data:
        reset_text = Text()
        reset_text.append("⏰ ", style="")
        reset_text.append(format_reset_time(limit_data.resets_at), style="yellow")
    else:
        reset_text = Text("⏳ Loading...", style="dim")

    table.add_row(title, reset_text)
    return table


def create_gauge_section(
    limit_data: LimitData | None,
    budget_pace: float,
) -> Table:
    """Create the 2-bar gauge section for a limit.

    Args:
        limit_data: Current limit data
        budget_pace: Percentage of window elapsed (0-1)

    Returns:
        Rich Table with Usage and Time Elapsed bars
    """
    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column(width=14)  # Label
    table.add_column(ratio=1)  # Bar
    table.add_column(width=8, justify="right")  # Value

    if limit_data is None:
        # Show empty/loading state
        table.add_row(
            Text("📊 Usage", style="dim"),
            ProgressBar(total=100, completed=0, style=Style(color="dim")),
            Text("--%", style="dim"),
        )
        table.add_row(
            Text("⏳ Elapsed", style="dim"),
            ProgressBar(total=100, completed=0, style=Style(color="dim")),
            Text("--%", style="dim"),
        )
        return table

    utilization_percent = limit_data.utilization * 100
    pace_percent = budget_pace * 100

    # Usage bar - color by threshold
    # complete_style = filled portion (bright), style = unfilled portion (dim)
    usage_color = get_utilization_color(limit_data.utilization)
    usage_bar = ProgressBar(
        total=100,
        completed=utilization_percent,
        style=Style(color="grey37"),  # Dim gray for unfilled
        complete_style=Style(color=usage_color),  # Bright color for filled
    )

    # Usage label - keep emoji consistent (⚠️ has inconsistent width across terminals)
    usage_label = Text()
    usage_label.append("📊 ", style="")
    usage_label.append("Usage", style=f"bold {usage_color}")

    table.add_row(
        usage_label,
        usage_bar,
        Text(f"{utilization_percent:.0f}%", style=usage_color),
    )

    # Time Elapsed bar - always blue
    # complete_style = filled portion (bright blue), style = unfilled portion (dim)
    elapsed_bar = ProgressBar(
        total=100,
        completed=pace_percent,
        style=Style(color="grey37"),  # Dim gray for unfilled
        complete_style=Style(color="blue"),  # Bright blue for filled
    )

    time_label = Text()
    time_label.append("⏳ ", style="")  # Use hourglass emoji (consistent width)
    time_label.append("Elapsed", style="bold blue")

    table.add_row(
        time_label,
        elapsed_bar,
        Text(f"{pace_percent:.0f}%", style="blue"),
    )

    return table


def create_compact_output(
    session: LimitData | None,
    weekly: LimitData | None,
    weekly_sonnet: LimitData | None,
    budget_pace_session: float,
) -> str:
    """Create compact single-line output for status bars.

    Format: Session: 🧊 62% (2h14m) | Weekly: 🔥 29% | Sonnet: 🧊 1%
    Emojis indicate pace: 🧊 (behind), 🔥 (on pace), 🚨 (ahead)

    Args:
        session: Session limit data
        weekly: Weekly limit data
        weekly_sonnet: Weekly sonnet limit data
        budget_pace_session: Budget pace for session (for status indicator)

    Returns:
        Single-line string for status bar
    """
    from ..utils.formatting import format_duration

    parts = []

    # Session with time remaining
    if session:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        minutes_left = int((session.resets_at - now).total_seconds() / 60)
        time_str = f"({format_duration(minutes_left)})" if minutes_left > 0 else ""
        pace = calculate_budget_pace(session.resets_at, session.window_hours)
        emoji = get_pace_emoji(session.utilization, pace)
        parts.append(f"Session: {emoji} {session.utilization*100:.0f}% {time_str}".strip())
    else:
        parts.append("Session: --")

    # Weekly
    if weekly:
        pace = calculate_budget_pace(weekly.resets_at, weekly.window_hours)
        emoji = get_pace_emoji(weekly.utilization, pace)
        parts.append(f"Weekly: {emoji} {weekly.utilization*100:.0f}%")
    else:
        parts.append("Weekly: --")

    # Sonnet
    if weekly_sonnet:
        pace = calculate_budget_pace(weekly_sonnet.resets_at, weekly_sonnet.window_hours)
        emoji = get_pace_emoji(weekly_sonnet.utilization, pace)
        parts.append(f"Sonnet: {emoji} {weekly_sonnet.utilization*100:.0f}%")
    else:
        parts.append("Sonnet: --")

    return " | ".join(parts)


def create_compact_output_with_indicator(
    session: LimitData | None,
    weekly: LimitData | None,
    weekly_sonnet: LimitData | None,
    budget_pace_session: float,
) -> str:
    """Create compact output with status indicator.

    Format: [!] 62% (2h14m) | 29% | 1%

    Args:
        session: Session limit data
        weekly: Weekly limit data
        weekly_sonnet: Weekly sonnet limit data
        budget_pace_session: Budget pace for session (for status indicator)

    Returns:
        Single-line string with status indicator
    """
    from ..utils.formatting import format_duration, get_status_indicator

    # Determine which limit is most critical
    max_util = 0.0
    if session:
        max_util = max(max_util, session.utilization)
    if weekly:
        max_util = max(max_util, weekly.utilization)
    if weekly_sonnet:
        max_util = max(max_util, weekly_sonnet.utilization)

    indicator = get_status_indicator(max_util, budget_pace_session)

    parts = [indicator]

    # Session with time remaining
    if session:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        minutes_left = int((session.resets_at - now).total_seconds() / 60)
        time_str = f"({format_duration(minutes_left)})" if minutes_left > 0 else ""
        parts.append(f"{session.utilization*100:.0f}% {time_str}".strip())
    else:
        parts.append("--")

    # Weekly
    if weekly:
        parts.append(f"{weekly.utilization*100:.0f}%")
    else:
        parts.append("--")

    # Sonnet
    if weekly_sonnet:
        parts.append(f"{weekly_sonnet.utilization*100:.0f}%")
    else:
        parts.append("--")

    return " | ".join(parts)
