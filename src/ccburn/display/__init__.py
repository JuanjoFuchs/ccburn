"""Display layer for ccburn - Rich-based TUI components."""

try:
    from .gauges import create_gauge_section, create_header
    from .chart import BurnupChart
    from .layout import BurnupLayout
except ImportError:
    from ccburn.display.gauges import create_gauge_section, create_header
    from ccburn.display.chart import BurnupChart
    from ccburn.display.layout import BurnupLayout

__all__ = [
    "create_gauge_section",
    "create_header",
    "BurnupChart",
    "BurnupLayout",
]
