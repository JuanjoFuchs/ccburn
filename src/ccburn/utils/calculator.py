"""Calculator utilities for burn rate, budget pace, and predictions."""

from datetime import datetime, timedelta, timezone

try:
    from ..data.models import BurnMetrics, LimitData, LimitType, MonthlyLimitData, UsageSnapshot
except ImportError:
    from ccburn.data.models import (
        BurnMetrics,
        LimitData,
        LimitType,
        MonthlyLimitData,
        UsageSnapshot,
    )


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
    window_start: datetime,
    window_hours: float,
    min_points: int = 3,
    min_span_pct: float = 0.10,
    recent_window_minutes: int | None = None,
) -> float:
    """Calculate burn rate as percentage points per hour using linear regression.

    Uses least-squares linear regression over snapshots from the current window
    for an accurate burn rate estimate.

    Args:
        snapshots: List of usage snapshots (should be sorted by timestamp)
        limit_type: Which limit to calculate burn rate for
        window_start: Start of the current window (from limit_data)
        window_hours: Duration of the window in hours
        min_points: Minimum data points required for regression (default 3)
        min_span_pct: Minimum time span as fraction of window (default 0.10 = 10%)

    Returns:
        Burn rate in percentage points per hour (e.g., 12.5 means 12.5%/hour)
        Returns 0.0 if insufficient data (no projection should be shown)
    """
    if len(snapshots) < 2:
        return 0.0

    cutoff = window_start
    if recent_window_minutes is not None:
        recent_cutoff = datetime.now(timezone.utc) - timedelta(minutes=recent_window_minutes)
        cutoff = max(cutoff, recent_cutoff)

    # Filter to snapshots within window and extract (time, utilization) pairs
    points: list[tuple[float, float]] = []  # (hours_from_start, utilization_pct)
    first_timestamp = None
    last_timestamp = None

    for s in snapshots:
        if s.timestamp < cutoff:
            continue
        limit = s.get_limit(limit_type)
        if limit is None:
            continue
        if first_timestamp is None:
            first_timestamp = s.timestamp
        last_timestamp = s.timestamp
        hours = (s.timestamp - first_timestamp).total_seconds() / 3600
        points.append((hours, limit.utilization * 100))

    # Need at least min_points for meaningful regression
    if len(points) < min_points:
        return 0.0

    # Check that data spans at least min_span_pct of the window
    # e.g., for 5h session at 10%, need 30 min of data
    # e.g., for 168h weekly at 10%, need ~17 hours of data
    # Cap at 6 hours max so monthly (744h) doesn't require 3+ days of data
    if first_timestamp and last_timestamp:
        span_hours = (last_timestamp - first_timestamp).total_seconds() / 3600
        effective_window_hours = (recent_window_minutes / 60) if recent_window_minutes is not None else window_hours
        min_span_hours = min(effective_window_hours * min_span_pct, 6.0)
        if span_hours < min_span_hours:
            return 0.0

    # If we have exactly 2 points, use simple slope
    if len(points) == 2:
        dx = points[1][0] - points[0][0]
        if dx <= 0:
            return 0.0
        return (points[1][1] - points[0][1]) / dx

    # Linear regression using least squares
    # slope = (n*Σxy - Σx*Σy) / (n*Σx² - (Σx)²)
    n = len(points)
    sum_x = sum(p[0] for p in points)
    sum_y = sum(p[1] for p in points)
    sum_xy = sum(p[0] * p[1] for p in points)
    sum_x2 = sum(p[0] ** 2 for p in points)

    denominator = n * sum_x2 - sum_x**2
    if abs(denominator) < 1e-10:
        # All x values are the same (no time elapsed)
        return 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return slope  # %/hour


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
    limit_data: LimitData | MonthlyLimitData,
    snapshots: list[UsageSnapshot],
    recent_window_minutes: int | None = None,
) -> BurnMetrics:
    """Calculate all burn metrics for a limit.

    Args:
        limit_data: Current limit data
        snapshots: Historical snapshots for burn rate calculation

    Returns:
        BurnMetrics with all calculated values
    """
    budget_pace = calculate_budget_pace(limit_data.resets_at, limit_data.window_hours)
    burn_rate = calculate_burn_rate(
        snapshots,
        limit_data.limit_type,
        window_start=limit_data.window_start,
        window_hours=limit_data.window_hours,
        recent_window_minutes=recent_window_minutes,
    )
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
