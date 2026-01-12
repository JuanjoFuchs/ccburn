"""Formatting utilities for ccburn."""

from datetime import datetime, timezone


def format_duration(minutes: int) -> str:
    """Format minutes as human-readable duration.

    Args:
        minutes: Duration in minutes

    Returns:
        Formatted string like "2h 14m", "3d 5h", "45m"
    """
    if minutes < 0:
        return "0m"

    if minutes < 60:
        return f"{minutes}m"

    hours = minutes // 60
    mins = minutes % 60

    if hours < 24:
        if mins:
            return f"{hours}h {mins}m"
        return f"{hours}h"

    days = hours // 24
    remaining_hours = hours % 24

    if remaining_hours:
        return f"{days}d {remaining_hours}h"
    return f"{days}d"


def format_percentage(value: float, decimal_places: int = 0) -> str:
    """Format 0-1 float as percentage string.

    Args:
        value: Float between 0 and 1
        decimal_places: Number of decimal places (default 0)

    Returns:
        Formatted string like "62%" or "62.5%"
    """
    percent = value * 100
    if decimal_places == 0:
        return f"{percent:.0f}%"
    return f"{percent:.{decimal_places}f}%"


def format_reset_time(resets_at: datetime, now: datetime | None = None) -> str:
    """Format reset time as relative or absolute.

    Args:
        resets_at: When the limit resets
        now: Current time (default: now)

    Returns:
        "Resets in 2h 14m" for < 24h, "Resets Tue 4:00 PM" otherwise
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Ensure both are timezone-aware
    if resets_at.tzinfo is None:
        resets_at = resets_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    delta = resets_at - now
    total_minutes = int(delta.total_seconds() / 60)

    if total_minutes < 0:
        return "Reset pending"

    if total_minutes < 24 * 60:  # Less than 24 hours
        return f"Resets in {format_duration(total_minutes)}"

    # More than 24 hours - use absolute time
    # Convert to local time for display
    local_time = resets_at.astimezone()
    day_name = local_time.strftime("%a")  # "Tue"
    # Use %I and strip leading zero (%-I is Unix-only, %#I is Windows-only)
    time_str = local_time.strftime("%I:%M %p").lstrip("0")  # "4:00 PM"
    return f"Resets {day_name} {time_str}"


def get_utilization_color(utilization: float) -> str:
    """Get color based on utilization percentage.

    Args:
        utilization: Float between 0 and 1

    Returns:
        Color name: "green", "yellow", "orange", or "red"
    """
    if utilization < 0.5:
        return "green"
    elif utilization < 0.75:
        return "yellow"
    elif utilization < 0.9:
        return "bright_red"  # Rich uses "bright_red" for orange-like
    else:
        return "red"


def get_status_indicator(utilization: float, budget_pace: float) -> str:
    """Get status indicator for compact output.

    Args:
        utilization: Current usage (0-1)
        budget_pace: How much of window has elapsed (0-1)

    Returns:
        Status indicator: "[ ]", "[*]", "[!]", or "[X]"
    """
    if utilization < 0.5:
        return "[ ]"  # Plenty available
    elif utilization < 0.75:
        if utilization <= budget_pace:
            return "[*]"  # On track
        return "[!]"  # Above pace
    elif utilization < 0.9:
        return "[!]"  # Caution
    else:
        return "[X]"  # Critical
