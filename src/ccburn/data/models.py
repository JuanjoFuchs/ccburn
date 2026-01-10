"""Data models for ccburn usage tracking."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class LimitType(str, Enum):
    """The three usage limits we track."""

    SESSION = "session"  # 5-hour rolling
    WEEKLY = "weekly"  # 7-day all models
    WEEKLY_SONNET = "weekly-sonnet"  # 7-day sonnet only

    @property
    def window_hours(self) -> int:
        """Get the window duration in hours."""
        return 5 if self == LimitType.SESSION else 168  # 7 * 24

    @property
    def display_name(self) -> str:
        """Get human-readable display name."""
        return {
            LimitType.SESSION: "Session (5h)",
            LimitType.WEEKLY: "Weekly",
            LimitType.WEEKLY_SONNET: "Weekly Sonnet",
        }[self]

    @property
    def api_field(self) -> str:
        """Get the corresponding API field name."""
        return {
            LimitType.SESSION: "five_hour",
            LimitType.WEEKLY: "seven_day",
            LimitType.WEEKLY_SONNET: "seven_day_sonnet",
        }[self]


@dataclass
class LimitData:
    """Data for a single usage limit."""

    utilization: float  # 0.0 to 1.0
    resets_at: datetime
    limit_type: LimitType

    @property
    def window_hours(self) -> int:
        """Get the window duration in hours."""
        return self.limit_type.window_hours

    @property
    def window_start(self) -> datetime:
        """Calculate when the current window started."""
        return self.resets_at - timedelta(hours=self.window_hours)

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
    raw_response: str | None = None  # Original JSON for debugging

    def get_limit(self, limit_type: LimitType) -> LimitData | None:
        """Get limit data by type."""
        return {
            LimitType.SESSION: self.session,
            LimitType.WEEKLY: self.weekly,
            LimitType.WEEKLY_SONNET: self.weekly_sonnet,
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

        return cls(
            timestamp=timestamp,
            session=parse_limit(data.get("five_hour"), LimitType.SESSION),
            weekly=parse_limit(data.get("seven_day"), LimitType.WEEKLY),
            weekly_sonnet=parse_limit(data.get("seven_day_sonnet"), LimitType.WEEKLY_SONNET),
            weekly_opus=weekly_opus,
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
