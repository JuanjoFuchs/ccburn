"""Progress bar gauges for ccburn TUI."""

import os
import sys

from rich.progress import ProgressBar
from rich.style import Style
from rich.table import Table
from rich.text import Text

try:
    from ..data.models import LimitData, LimitType, MonthlyLimitData
    from ..utils.calculator import calculate_budget_pace
    from ..utils.formatting import format_reset_time, get_utilization_color
except ImportError:
    from ccburn.data.models import LimitData, LimitType, MonthlyLimitData
    from ccburn.utils.calculator import calculate_budget_pace
    from ccburn.utils.formatting import format_reset_time, get_utilization_color


_emoji_support_cache: bool | None = None


def _supports_emoji() -> bool:
    """Detect if the console supports emoji characters.

    Result is cached to ensure consistent behavior throughout the session,
    as Rich's Live mode may affect stdout properties during rendering.

    Returns:
        True if emoji are likely supported, False otherwise.
    """
    global _emoji_support_cache
    if _emoji_support_cache is not None:
        return _emoji_support_cache

    # First, check if stdout encoding can handle emoji - this prevents crashes
    # even in modern terminals if Python's encoding is misconfigured
    try:
        encoding = getattr(sys.stdout, "encoding", None) or ""
        if encoding.lower() not in ("utf-8", "utf8"):
            # Try to encode an emoji to test
            "🔥".encode(encoding)
    except (UnicodeEncodeError, LookupError):
        # Encoding cannot handle emoji - use ASCII to prevent crashes
        _emoji_support_cache = False
        return False

    # Encoding is OK, now check for modern terminal environments
    # that are known to render emoji correctly
    if os.environ.get("WT_SESSION"):  # Windows Terminal
        _emoji_support_cache = True
        return True
    if os.environ.get("TERM_PROGRAM"):  # macOS Terminal, iTerm2, VS Code, etc.
        _emoji_support_cache = True
        return True
    if os.environ.get("COLORTERM") == "truecolor":  # Modern terminals with truecolor
        _emoji_support_cache = True
        return True

    # Fall back to utf-8 encoding check
    encoding = getattr(sys.stdout, "encoding", None) or ""
    _emoji_support_cache = encoding.lower() in ("utf-8", "utf8")
    return _emoji_support_cache


def format_credits(dollars: float) -> str:
    """Format dollar amount for display.

    Args:
        dollars: Amount in dollars

    Returns:
        Formatted string like "$74.75" or "$1,234"
    """
    if dollars >= 1000:
        return f"${dollars:,.0f}"
    elif dollars >= 100:
        return f"${dollars:.0f}"
    else:
        return f"${dollars:.2f}"


def get_pace_emoji(utilization: float, budget_pace: float, ascii_fallback: bool = False) -> str:
    """Get emoji indicator based on utilization vs budget pace.

    Args:
        utilization: Current utilization (0-1)
        budget_pace: Expected budget pace (0-1)
        ascii_fallback: If True, use ASCII characters instead of emoji

    Returns:
        Emoji: 🧊 (behind), 🔥 (on pace), 🚨 (ahead)
        ASCII: [_] (behind), [=] (on pace), [!] (ahead)
    """
    use_ascii = ascii_fallback or not _supports_emoji()

    if budget_pace == 0:
        return "[=]" if use_ascii else "🔥"

    ratio = utilization / budget_pace
    if ratio < 0.85:
        return "[_]" if use_ascii else "🧊"  # Behind pace - ice cold, under budget
    elif ratio > 1.15:
        return "[!]" if use_ascii else "🚨"  # Ahead of pace - alarm!
    else:
        return "[=]" if use_ascii else "🔥"  # On pace - normal burn


def create_header(
    limit_type: LimitType, limit_data: LimitData | MonthlyLimitData | None
) -> Table:
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
    limit_data: LimitData | MonthlyLimitData | None,
    budget_pace: float,
) -> Table:
    """Create the 2-bar gauge section for a limit.

    Args:
        limit_data: Current limit data (LimitData or MonthlyLimitData)
        budget_pace: Percentage of window elapsed (0-1)

    Returns:
        Rich Table with Usage and Time Elapsed bars
    """
    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column(width=14)  # Label
    table.add_column(ratio=1)  # Bar
    table.add_column(width=18, justify="right")  # Value (wider for dollar amounts)

    if limit_data is None:
        # Show empty/loading state
        table.add_row(
            Text("📊 Usage", style="dim"),
            ProgressBar(total=100, completed=0, style=Style(color="grey37")),
            Text("--%", style="dim"),
        )
        table.add_row(
            Text("⏳ Elapsed", style="dim"),
            ProgressBar(total=100, completed=0, style=Style(color="grey37")),
            Text("--%", style="dim"),
        )
        return table

    utilization_percent = limit_data.utilization * 100
    pace_percent = budget_pace * 100

    # Usage bar - color by threshold AND burn rate
    # complete_style = filled portion (bright), style = unfilled portion (dim)
    usage_color = get_utilization_color(limit_data.utilization, budget_pace)
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

    # Format value text - dollars for monthly, percentage for others
    if isinstance(limit_data, MonthlyLimitData):
        used = format_credits(limit_data.used_credits_dollars)
        total = format_credits(limit_data.monthly_limit_dollars)
        value_text = Text(f"{used} / {total}", style=usage_color)
    else:
        value_text = Text(f"{utilization_percent:.0f}%", style=usage_color)

    table.add_row(
        usage_label,
        usage_bar,
        value_text,
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
    monthly: MonthlyLimitData | None,
    budget_pace_session: float,
) -> str:
    """Create compact single-line output for status bars.

    Format: Session: 🧊 62% (2h14m) | Weekly: 🔥 29% | Sonnet: 🧊 1% | Monthly: 🧊 $74.75
    Emojis indicate pace: 🧊 (behind), 🔥 (on pace), 🚨 (ahead)

    Args:
        session: Session limit data
        weekly: Weekly limit data
        weekly_sonnet: Weekly sonnet limit data
        monthly: Monthly credits data
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

    # Weekly
    if weekly:
        pace = calculate_budget_pace(weekly.resets_at, weekly.window_hours)
        emoji = get_pace_emoji(weekly.utilization, pace)
        parts.append(f"Weekly: {emoji} {weekly.utilization*100:.0f}%")

    # Sonnet
    if weekly_sonnet:
        pace = calculate_budget_pace(weekly_sonnet.resets_at, weekly_sonnet.window_hours)
        emoji = get_pace_emoji(weekly_sonnet.utilization, pace)
        parts.append(f"Sonnet: {emoji} {weekly_sonnet.utilization*100:.0f}%")

    # Monthly credits
    if monthly:
        pace = calculate_budget_pace(monthly.resets_at, monthly.window_hours)
        emoji = get_pace_emoji(monthly.utilization, pace)
        dollars = format_credits(monthly.used_credits_dollars)
        parts.append(f"Monthly: {emoji} {dollars}")

    # If nothing available, show placeholder
    if not parts:
        parts.append("No data available")

    return " · ".join(parts)


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

    return " · ".join(parts)
