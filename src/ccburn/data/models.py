"""Data models for ccburn usage tracking."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class LimitType(str, Enum):
    """The usage limits we track."""

    SESSION = "session"  # 5-hour rolling
    WEEKLY = "weekly"  # 7-day all models
    WEEKLY_SONNET = "weekly-sonnet"  # 7-day sonnet only
    MONTHLY = "monthly"  # Monthly credits (enterprise)

    @property
    def window_hours(self) -> int | None:
        """Get the window duration in hours. None for variable-length windows."""
        if self == LimitType.SESSION:
            return 5
        elif self == LimitType.MONTHLY:
            return None  # Variable - calculated at runtime based on month
        else:
            return 168  # 7 * 24

    @property
    def display_name(self) -> str:
        """Get human-readable display name."""
        return {
            LimitType.SESSION: "Session (5h)",
            LimitType.WEEKLY: "Weekly",
            LimitType.WEEKLY_SONNET: "Weekly Sonnet",
            LimitType.MONTHLY: "Monthly Credits",
        }[self]

    @property
    def api_field(self) -> str | None:
        """Get the corresponding API field name. None for extra_usage-based types."""
        return {
            LimitType.SESSION: "five_hour",
            LimitType.WEEKLY: "seven_day",
            LimitType.WEEKLY_SONNET: "seven_day_sonnet",
            LimitType.MONTHLY: None,  # Uses extra_usage block
        }.get(self)


@dataclass
class LimitData:
    """Data for a single usage limit."""

    utilization: float  # 0.0 to 1.0
    resets_at: datetime
    limit_type: LimitType

    @property
    def window_hours(self) -> int:
        """Get the window duration in hours."""
        hours = self.limit_type.window_hours
        return hours if hours is not None else 168  # Fallback for type safety

    @property
    def window_start(self) -> datetime:
        """Calculate when the current window started."""
        return self.resets_at - timedelta(hours=self.window_hours)

    @property
    def utilization_percent(self) -> float:
        """Get utilization as a percentage (0-100)."""
        return self.utilization * 100


@dataclass
class MonthlyLimitData:
    """Data for monthly credit usage (enterprise accounts)."""

    monthly_limit_cents: int  # e.g., 30000 = $300.00
    used_credits_cents: float  # e.g., 7475.0 = $74.75
    utilization: float  # 0.0 to 1.0 normalized
    resets_at: datetime  # 1st of next month UTC
    limit_type: LimitType = LimitType.MONTHLY

    @property
    def monthly_limit_dollars(self) -> float:
        """Get monthly limit in dollars."""
        return self.monthly_limit_cents / 100.0

    @property
    def used_credits_dollars(self) -> float:
        """Get used credits in dollars."""
        return self.used_credits_cents / 100.0

    @property
    def remaining_dollars(self) -> float:
        """Get remaining credits in dollars."""
        return self.monthly_limit_dollars - self.used_credits_dollars

    @property
    def window_hours(self) -> int:
        """Get days in current month * 24."""
        now = datetime.now(timezone.utc)
        first_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        days_in_month = (self.resets_at - first_of_month).days
        return days_in_month * 24

    @property
    def window_start(self) -> datetime:
        """1st of current month at 00:00 UTC."""
        now = datetime.now(timezone.utc)
        return datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    @property
    def utilization_percent(self) -> float:
        """Get utilization as a percentage (0-100)."""
        return self.utilization * 100


@dataclass
class UsageSnapshot:
    """A point-in-time snapshot of all usage limits."""

    timestamp: datetime
    session: LimitData | None  # five_hour from API
    weekly: LimitData | None  # seven_day from API
    weekly_sonnet: LimitData | None  # seven_day_sonnet from API
    weekly_opus: LimitData | None  # seven_day_opus from API (tracked but not displayed)
    monthly: MonthlyLimitData | None = None  # extra_usage from API (enterprise)
    raw_response: str | None = None  # Original JSON for debugging

    def get_limit(self, limit_type: LimitType) -> LimitData | MonthlyLimitData | None:
        """Get limit data by type."""
        return {
            LimitType.SESSION: self.session,
            LimitType.WEEKLY: self.weekly,
            LimitType.WEEKLY_SONNET: self.weekly_sonnet,
            LimitType.MONTHLY: self.monthly,
        }.get(limit_type)

    @classmethod
    def from_api_response(cls, data: dict, timestamp: datetime | None = None) -> "UsageSnapshot":
        """Create a UsageSnapshot from API response data."""
        import json

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        def parse_limit(api_data: dict | None, limit_type: LimitType) -> LimitData | None:
            if not api_data or not isinstance(api_data, dict):
                return None
            utilization = api_data.get("utilization")
            resets_at_str = api_data.get("resets_at")
            if utilization is None or resets_at_str is None:
                return None
            try:
                resets_at = datetime.fromisoformat(resets_at_str.replace("Z", "+00:00"))
                # API returns 0-100 scale, normalize to 0-1
                util_normalized = float(utilization) / 100.0
                return LimitData(
                    utilization=util_normalized,
                    resets_at=resets_at,
                    limit_type=limit_type,
                )
            except (ValueError, TypeError):
                return None

        # Parse weekly opus separately (uses same window as weekly)
        opus_data = data.get("seven_day_opus")
        weekly_opus = None
        if opus_data and isinstance(opus_data, dict):
            utilization = opus_data.get("utilization")
            resets_at_str = opus_data.get("resets_at")
            if utilization is not None and resets_at_str:
                try:
                    resets_at = datetime.fromisoformat(resets_at_str.replace("Z", "+00:00"))
                    # API returns 0-100 scale, normalize to 0-1
                    # Create a pseudo LimitType for opus (uses weekly window)
                    weekly_opus = LimitData(
                        utilization=float(utilization) / 100.0,
                        resets_at=resets_at,
                        limit_type=LimitType.WEEKLY,  # Same window as weekly
                    )
                except (ValueError, TypeError):
                    pass

        # Parse monthly credits from extra_usage (enterprise accounts)
        monthly = None
        extra_usage = data.get("extra_usage")
        if extra_usage and isinstance(extra_usage, dict):
            if extra_usage.get("is_enabled") and extra_usage.get("monthly_limit"):
                try:
                    monthly_limit = int(extra_usage["monthly_limit"])
                    used_credits = float(extra_usage.get("used_credits", 0))
                    utilization_pct = float(extra_usage.get("utilization", 0))

                    # Calculate resets_at as 1st of next month UTC
                    now = datetime.now(timezone.utc)
                    if now.month == 12:
                        resets_at = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
                    else:
                        resets_at = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

                    monthly = MonthlyLimitData(
                        monthly_limit_cents=monthly_limit,
                        used_credits_cents=used_credits,
                        utilization=utilization_pct / 100.0,  # Normalize to 0-1
                        resets_at=resets_at,
                    )
                except (ValueError, TypeError, KeyError):
                    pass

        return cls(
            timestamp=timestamp,
            session=parse_limit(data.get("five_hour"), LimitType.SESSION),
            weekly=parse_limit(data.get("seven_day"), LimitType.WEEKLY),
            weekly_sonnet=parse_limit(data.get("seven_day_sonnet"), LimitType.WEEKLY_SONNET),
            weekly_opus=weekly_opus,
            monthly=monthly,
            raw_response=json.dumps(data),
        )


@dataclass
class BurnMetrics:
    """Calculated burn rate metrics for a specific limit."""

    limit_type: LimitType
    percent_per_hour: float
    trend: str  # "low", "moderate", "high", "critical"
    estimated_minutes_to_100: int | None
    budget_pace: float  # 0.0 to 1.0 - what percentage of window has elapsed
    status: str  # "ahead_of_pace", "on_pace", "behind_pace"
    recommendation: str  # "plenty_available", "on_track", "moderate_pace", "conserve", "critical"
