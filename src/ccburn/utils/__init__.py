"""Utilities for ccburn - calculators and formatters."""

try:
    from .calculator import (
        calculate_budget_pace,
        calculate_burn_metrics,
        calculate_burn_rate,
        classify_burn_trend,
        estimate_time_to_empty,
        get_recommendation,
    )
    from .formatting import (
        format_duration,
        format_percentage,
        format_reset_time,
        get_utilization_color,
    )
except ImportError:
    from ccburn.utils.calculator import (
        calculate_budget_pace,
        calculate_burn_metrics,
        calculate_burn_rate,
        classify_burn_trend,
        estimate_time_to_empty,
        get_recommendation,
    )
    from ccburn.utils.formatting import (
        format_duration,
        format_percentage,
        format_reset_time,
        get_utilization_color,
    )

__all__ = [
    "format_duration",
    "format_percentage",
    "format_reset_time",
    "get_utilization_color",
    "calculate_budget_pace",
    "calculate_burn_rate",
    "estimate_time_to_empty",
    "classify_burn_trend",
    "get_recommendation",
    "calculate_burn_metrics",
]
