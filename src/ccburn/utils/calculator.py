"""Calculator utilities for burn rate, budget pace, and predictions."""

from datetime import datetime, timedelta, timezone

try:
    from ..data.models import LimitData, LimitType, UsageSnapshot, BurnMetrics
except ImportError:
    from ccburn.data.models import LimitData, LimitType, UsageSnapshot, BurnMetrics


def calculate_budget_pace(resets_at: datetime, window_hours: float) -> float:
    """Calculate what percentage of the window has elapsed.

    Formula: (now - window_start) / window_duration
    Where: window_start = resets_at - window_hours

    Args:
        resets_at: When the limit resets
        window_hours: Duration of the window in hours

    Returns:
        Float between 0.0 and 1.0 representing elapsed fraction
    """
    now = datetime.now(timezone.utc)

    # Ensure resets_at is timezone-aware
    if resets_at.tzinfo is None:
        resets_at = resets_at.replace(tzinfo=timezone.utc)

    window_start = resets_at - timedelta(hours=window_hours)
    elapsed = (now - window_start).total_seconds()
    window_seconds = window_hours * 3600

    if window_seconds <= 0:
        return 0.0

    pace = elapsed / window_seconds
    return max(0.0, min(1.0, pace))  # Clamp 0-1


def calculate_burn_rate(
    snapshots: list[UsageSnapshot],
    limit_type: LimitType,
    window_minutes: int = 5,
) -> float:
    """Calculate burn rate as percentage points per hour.

    Uses simple linear calculation over recent snapshots.

    Args:
        snapshots: List of usage snapshots (should be sorted by timestamp)
        limit_type: Which limit to calculate burn rate for
        window_minutes: How far back to look for calculation

    Returns:
        Burn rate in percentage points per hour (e.g., 12.5 means 12.5%/hour)
    """
    if len(snapshots) < 2:
        return 0.0

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=window_minutes)

    # Filter to recent snapshots
    recent = [s for s in snapshots if s.timestamp >= cutoff]

    if len(recent) < 2:
        # Fall back to any 2 snapshots if not enough recent ones
        recent = snapshots[-2:] if len(snapshots) >= 2 else []

    if len(recent) < 2:
        return 0.0

    # Get utilization for the specified limit type
    first = recent[0]
    last = recent[-1]

    first_limit = first.get_limit(limit_type)
    last_limit = last.get_limit(limit_type)

    if first_limit is None or last_limit is None:
        return 0.0

    delta_util = (last_limit.utilization - first_limit.utilization) * 100  # Convert to %
    delta_hours = (last.timestamp - first.timestamp).total_seconds() / 3600

    if delta_hours <= 0:
        return 0.0

    return delta_util / delta_hours  # %/hour


def estimate_time_to_empty(current_utilization: float, burn_rate_per_hour: float) -> int | None:
    """Estimate minutes until 100% utilization at current burn rate.

    Args:
        current_utilization: Current utilization (0-1)
        burn_rate_per_hour: Burn rate in percentage points per hour

    Returns:
        Minutes until 100%, or None if burn rate is zero or negative
    """
    if burn_rate_per_hour <= 0:
        return None

    remaining = 100.0 - (current_utilization * 100)
    if remaining <= 0:
        return 0

    hours_to_empty = remaining / burn_rate_per_hour
    return int(hours_to_empty * 60)


def classify_burn_trend(burn_rate_per_hour: float) -> str:
    """Classify burn rate into human-readable trend.

    Args:
        burn_rate_per_hour: Burn rate in percentage points per hour

    Returns:
        One of: "low", "moderate", "high", "critical"
    """
    if burn_rate_per_hour < 5:
        return "low"
    elif burn_rate_per_hour < 15:
        return "moderate"
    elif burn_rate_per_hour < 30:
        return "high"
    else:
        return "critical"


def get_recommendation(utilization: float, budget_pace: float) -> str:
    """Get recommendation based on utilization and budget pace.

    Args:
        utilization: Current utilization (0-1)
        budget_pace: How much of window has elapsed (0-1)

    Returns:
        One of: "plenty_available", "on_track", "moderate_pace", "conserve", "critical"
    """
    if utilization > 0.9:
        return "critical"
    elif utilization > 0.75:
        return "conserve"
    elif utilization > 0.5:
        if utilization <= budget_pace:
            return "on_track"
        return "moderate_pace"
    else:
        return "plenty_available"


def get_status(utilization: float, budget_pace: float) -> str:
    """Get pace status.

    Args:
        utilization: Current utilization (0-1)
        budget_pace: How much of window has elapsed (0-1)

    Returns:
        One of: "ahead_of_pace", "on_pace", "behind_pace"
    """
    # "ahead" means using more than expected (bad)
    # "behind" means using less than expected (good)
    diff = utilization - budget_pace

    if abs(diff) < 0.05:  # Within 5% tolerance
        return "on_pace"
    elif diff > 0:
        return "ahead_of_pace"
    else:
        return "behind_pace"


def calculate_burn_metrics(
    limit_data: LimitData,
    snapshots: list[UsageSnapshot],
    window_minutes: int = 5,
) -> BurnMetrics:
    """Calculate all burn metrics for a limit.

    Args:
        limit_data: Current limit data
        snapshots: Historical snapshots for burn rate calculation
        window_minutes: How far back to look for burn rate

    Returns:
        BurnMetrics with all calculated values
    """
    budget_pace = calculate_budget_pace(limit_data.resets_at, limit_data.window_hours)
    burn_rate = calculate_burn_rate(snapshots, limit_data.limit_type, window_minutes)
    time_to_empty = estimate_time_to_empty(limit_data.utilization, burn_rate)
    trend = classify_burn_trend(burn_rate)
    status = get_status(limit_data.utilization, budget_pace)
    recommendation = get_recommendation(limit_data.utilization, budget_pace)

    return BurnMetrics(
        limit_type=limit_data.limit_type,
        percent_per_hour=burn_rate,
        trend=trend,
        estimated_minutes_to_100=time_to_empty,
        budget_pace=budget_pace,
        status=status,
        recommendation=recommendation,
    )
