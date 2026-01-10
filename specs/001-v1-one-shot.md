# ccburn v1.0 Specification

## Overview

ccburn is a terminal-based tool for visualizing Claude Code usage limits with real-time burn-up charts. It provides immediate visibility into 5-hour rolling and 7-day usage limits without requiring a full observability stack.

- **Language/runtime**: Python 3.8+
- **CLI framework**: Typer (with rich_markup_mode for formatted help and auto-completion support)
- **TUI/rendering**: Rich (Live, Layout, Table) + Plotext for terminal charts (custom PlotextMixin implementing JupyterMixin)
- **Data source**: Anthropic Usage API (OAuth)
- **Data storage**: SQLite for historical snapshots (`~/.ccburn/history.db`)
- **Version management**: Dynamic version via `importlib.metadata.version("ccburn")` from pyproject.toml
- **Entry point**: Console script `ccburn` -> `ccburn.main:app`
- **Distribution**: PyPI (pip install)

## Background & Motivation

### The Problem

Claude Code users have no easy way to visualize their usage limit consumption over time. The existing options are:

1. **`/usage` command** - Shows current state, no history, no visualization
2. **ccusage** - Excellent for cost/token tables, but no charts and doesn't show actual limit utilization
3. **Grafana dashboards** - Requires running a full observability stack (Docker, Prometheus, Grafana)

### Key Finding: OTEL Metrics Don't Predict Limits

Correlation analysis between OTEL metrics and usage limit burn rate showed **all correlations were weak (|r| < 0.3)**.

Why? OTEL metrics are missing **thinking tokens** - the invisible reasoning tokens that can be 3-10x the visible output and count fully against usage limits.

| What OTEL Tracks | What Counts Toward Limits |
|------------------|---------------------------|
| input, output, cacheRead, cacheCreation | All of those PLUS thinking tokens |

Other factors not in OTEL:
- **Model weighting**: Opus consumes ~5x more allocation than Sonnet
- **Cross-product usage**: claude.ai, Claude Code, and Desktop share limits
- **Thinking budget keywords**: "think hard", "ultrathink" increase consumption

### Implication

The **Usage API** is the only source of truth for limit consumption. ccburn focuses exclusively on Usage API data.

## Core Goals and Behaviors

- **Standalone operation**: No Docker, Prometheus, Grafana, or external services required
- **Self-contained history**: SQLite database builds up charts over time as you use ccburn
- **Two modes**: Human-readable TUI and JSON output for programmatic use
- **Complement ccusage**: Different data sources, different questions answered

| Tool | Purpose |
|------|---------|
| **ccusage** | "What did I spend?" - tokens, costs, by model, from JSONL |
| **ccburn** | "How close am I to the limit?" - burn rate, time left, charts |

## Technical Architecture

### Source Layout

```
ccburn/
├── pyproject.toml
├── README.md
├── LICENSE (MIT)
├── src/
│   └── ccburn/
│       ├── __init__.py
│       ├── main.py              # Entry point and Typer app
│       ├── cli.py               # Typer command definitions
│       ├── data/
│       │   ├── __init__.py
│       │   ├── usage_client.py  # Anthropic Usage API client
│       │   ├── credentials.py   # OAuth token reader
│       │   └── history.py       # SQLite storage
│       ├── display/
│       │   ├── __init__.py
│       │   ├── chart.py         # Plotext burnup chart
│       │   ├── table.py         # Rich statistics table
│       │   └── layout.py        # UI layout management
│       └── utils/
│           ├── __init__.py
│           ├── calculator.py    # Burn rate, budget pace, predictions
│           └── formatting.py    # Time/percentage formatting
├── tests/
│   ├── __init__.py
│   ├── test_calculator.py
│   ├── test_history.py
│   └── test_usage_client.py
└── specs/
    └── v1.md
```

### Layers

- **CLI layer** (`cli.py`): Typer-based argument parsing/validation, dispatch to app
- **App orchestration** (`main.py`): CCBurnApp class managing lifecycle, Rich Live loop, signal handlers (SIGINT/SIGTERM), resource cleanup
- **Data layer** (`data/`): UsageClient for API calls, History for SQLite, Credentials for OAuth tokens
- **Display layer** (`display/`): BurnupLayout with responsive sizing, StatsTable, PlotextMixin for chart integration
- **Utilities** (`utils/`): BurnRateCalculator for predictions, formatting helpers

### Dependencies

**Core (minimal)**:
- `typer[all]` - CLI framework with rich support
- `rich` - Terminal UI rendering
- `plotext` - Terminal plotting

**Standard library (zero deps)**:
- `sqlite3` - History storage
- `urllib.request` - HTTP client
- `json` - API response parsing
- `argparse` - (via Typer)

## Usage API Integration

### Endpoint

```
GET https://api.anthropic.com/api/oauth/usage
Authorization: Bearer {accessToken}
anthropic-beta: oauth-2025-04-20
```

### Credentials Location

```
~/.claude/.credentials.json
```

Structure:
```json
{
  "claudeAiOauth": {
    "accessToken": "...",
    "refreshToken": "...",
    "expiresAt": "..."
  }
}
```

### API Response Structure

```json
{
  "five_hour": {
    "utilization": 0.62,
    "resets_at": "2026-01-08T16:46:00Z"
  },
  "seven_day": {
    "utilization": 0.42,
    "resets_at": "2026-01-12T00:00:00Z"
  },
  "seven_day_sonnet": {
    "utilization": 0.38,
    "resets_at": "2026-01-12T00:00:00Z"
  },
  "seven_day_opus": {
    "utilization": 0.15,
    "resets_at": "2026-01-12T00:00:00Z"
  },
  "extra_usage": {
    "is_enabled": false,
    "utilization": null
  }
}
```

### Error Handling

| Scenario | Behavior |
|----------|----------|
| No credentials file | Exit with helpful error message pointing to Claude Code login |
| Token expired | Prompt user to restart Claude Code to refresh token |
| API returns error | Show warning, continue with stale data from history |
| Network error | Show warning, retry with exponential backoff (max 3 retries) |
| API returns null fields | Show "N/A", continue with available data |

## CLI Interface

### Commands

Following ccusage pattern: **subcommands for limit types**, **flags for modifiers**.

```bash
# Live TUI mode (default) - 5h session limit, updates every 30s
ccburn

# Subcommands: select which limit to display
ccburn session         # 5-hour rolling (default if no subcommand)
ccburn weekly          # 7-day all models
ccburn weekly-sonnet   # 7-day sonnet only

# Flags: modifiers that work with any subcommand
ccburn session --since 2h        # Zoom to last 2 hours
ccburn weekly --since 24h        # 7-day limit, last 24h view
ccburn weekly-sonnet --since 7d  # Full week view

# Output modes
ccburn --json                    # JSON snapshot (default limit: session)
ccburn weekly --json             # JSON for 7-day all models
ccburn --once                    # Print once and exit
ccburn --compact                 # Single-line for status bars/tmux

# Other options
ccburn --interval 60             # Refresh every 60s (default: 30s)
ccburn --clear-history           # Clear stored SQLite history
ccburn --debug                   # Show raw API response
ccburn --version                 # Version info
```

### Subcommand Details

| Subcommand | Limit | Window | Description |
|------------|-------|--------|-------------|
| `session` | 5-hour rolling | 5h | Current session limit (default) |
| `weekly` | 7-day all models | 168h | Weekly budget across all models |
| `weekly-sonnet` | 7-day sonnet | 168h | Weekly Sonnet-only budget |

### CLI Framework: Typer

Following hwinfo-tui patterns:
- Type hints for automatic validation
- Shell auto-completion for bash, zsh, fish, PowerShell
- Rich help messages with examples
- Version callback using `importlib.metadata`

### JSON Output Format

```json
{
  "timestamp": "2026-01-08T14:32:00Z",
  "limits": {
    "session": {
      "utilization": 0.62,
      "budget_pace": 0.45,
      "resets_at": "2026-01-08T16:46:00Z",
      "resets_in_minutes": 134,
      "window_hours": 5,
      "status": "ahead_of_pace"
    },
    "weekly": {
      "utilization": 0.29,
      "budget_pace": 0.276,
      "resets_at": "2026-01-14T15:59:00Z",
      "resets_in_hours": 123,
      "window_hours": 168,
      "status": "ahead_of_pace"
    },
    "weekly-sonnet": {
      "utilization": 0.01,
      "budget_pace": 0.276,
      "resets_at": "2026-01-14T15:59:00Z",
      "resets_in_hours": 123,
      "window_hours": 168,
      "status": "on_pace"
    }
  },
  "burn_rate": {
    "limit": "session",
    "percent_per_hour": 12.5,
    "trend": "moderate",
    "estimated_minutes_to_100": 182
  },
  "recommendation": "moderate_pace"
}
```

### Compact Output Format

For embedding in status bars or tmux (all 3 limits on one line):

```
Session: 62% (2h14m) | Weekly: 29% | Sonnet: 1%
```

Or with status indicator for the most critical limit:
```
[!] 62% (2h14m) | 29% | 1%
```

Status indicators (based on highest utilization):
- `[ ]` - plenty available (<50%)
- `[*]` - on track (50-75%, below pace)
- `[!]` - caution (50-75%, above pace OR 75-90%)
- `[X]` - critical (>90%)

## Data Model

### SQLite Schema

```sql
-- Usage snapshots from API polling
CREATE TABLE usage_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,  -- ISO 8601 UTC

    -- 5-hour rolling
    five_hour_utilization REAL,
    five_hour_resets_at TEXT,

    -- 7-day all models
    seven_day_all_utilization REAL,
    seven_day_all_resets_at TEXT,

    -- 7-day sonnet
    seven_day_sonnet_utilization REAL,
    seven_day_sonnet_resets_at TEXT,

    -- 7-day opus
    seven_day_opus_utilization REAL,
    seven_day_opus_resets_at TEXT,

    -- Raw API response for debugging
    raw_response TEXT
);

CREATE INDEX idx_snapshots_timestamp ON usage_snapshots(timestamp);

-- Metadata
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

### Retention Policy

- Keep last 7 days of data
- Auto-prune on startup (delete WHERE timestamp < now - 7 days)
- ~10KB per day at 30s intervals (~2880 rows/day)

### Data Classes

```python
from enum import Enum

class LimitType(str, Enum):
    """The three usage limits we track."""
    SESSION = "session"              # 5-hour rolling
    WEEKLY = "weekly"                # 7-day all models
    WEEKLY_SONNET = "weekly-sonnet"  # 7-day sonnet only

    @property
    def window_hours(self) -> int:
        return 5 if self == LimitType.SESSION else 168  # 7 * 24

    @property
    def display_name(self) -> str:
        return {
            LimitType.SESSION: "Session (5h)",
            LimitType.WEEKLY: "Weekly",
            LimitType.WEEKLY_SONNET: "Weekly Sonnet",
        }[self]

@dataclass
class LimitData:
    """Data for a single usage limit."""
    utilization: float  # 0.0 to 1.0
    resets_at: datetime
    limit_type: LimitType

    @property
    def window_hours(self) -> int:
        return self.limit_type.window_hours

    @property
    def window_start(self) -> datetime:
        return self.resets_at - timedelta(hours=self.window_hours)

@dataclass
class UsageSnapshot:
    """A point-in-time snapshot of all usage limits."""
    timestamp: datetime
    session: LimitData | None       # five_hour from API
    all_models: LimitData | None    # seven_day from API
    sonnet: LimitData | None        # seven_day_sonnet from API
    opus: LimitData | None          # seven_day_opus from API (tracked but not displayed)

@dataclass
class BurnMetrics:
    """Calculated burn rate metrics for a specific limit."""
    limit_type: LimitType
    percent_per_hour: float
    trend: str  # "low", "moderate", "high", "critical"
    estimated_minutes_to_100: int | None
    budget_pace: float  # 0.0 to 1.0
    status: str  # "ahead_of_pace", "on_pace", "behind_pace"
```

## Calculator Logic

### Budget Pace Calculation

From Grafana dashboard analysis:

```python
def calculate_budget_pace(resets_at: datetime, window_hours: float) -> float:
    """
    Calculate what percentage of the window has elapsed.

    Formula: (now - window_start) / window_duration * 100
    Where: window_start = resets_at - window_hours
    """
    now = datetime.now(timezone.utc)
    window_start = resets_at - timedelta(hours=window_hours)
    elapsed = (now - window_start).total_seconds()
    window_seconds = window_hours * 3600

    pace = (elapsed / window_seconds) * 100
    return max(0.0, min(100.0, pace))  # Clamp 0-100
```

### Burn Rate Calculation

From Grafana: `deriv(utilization[2m]) * 60` = %/minute

```python
def calculate_burn_rate(snapshots: list[UsageSnapshot], window_minutes: int = 5) -> float:
    """
    Calculate burn rate as percentage points per hour.

    Uses linear regression over recent snapshots for stability.
    """
    if len(snapshots) < 2:
        return 0.0

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    recent = [s for s in snapshots if s.timestamp >= cutoff]

    if len(recent) < 2:
        return 0.0

    # Simple: (last - first) / time_delta
    first, last = recent[0], recent[-1]
    delta_util = (last.five_hour.utilization - first.five_hour.utilization) * 100
    delta_hours = (last.timestamp - first.timestamp).total_seconds() / 3600

    if delta_hours == 0:
        return 0.0

    return delta_util / delta_hours  # %/hour
```

### Time-to-Empty Prediction

```python
def estimate_time_to_empty(current_utilization: float, burn_rate_per_hour: float) -> int | None:
    """
    Estimate minutes until 100% utilization at current burn rate.
    Returns None if burn rate is zero or negative.
    """
    if burn_rate_per_hour <= 0:
        return None

    remaining = (100.0 - current_utilization * 100)
    hours_to_empty = remaining / burn_rate_per_hour
    return int(hours_to_empty * 60)
```

### Trend Classification

```python
def classify_burn_trend(burn_rate_per_hour: float) -> str:
    """Classify burn rate into human-readable trend."""
    if burn_rate_per_hour < 5:
        return "low"
    elif burn_rate_per_hour < 15:
        return "moderate"
    elif burn_rate_per_hour < 30:
        return "high"
    else:
        return "critical"
```

### Recommendation Logic

| Utilization | vs Budget Pace | Recommendation |
|-------------|----------------|----------------|
| < 50% | Any | `plenty_available` |
| 50-75% | Below pace | `on_track` |
| 50-75% | Above pace | `moderate_pace` |
| 75-90% | Any | `conserve` |
| > 90% | Any | `critical` |

## Visual Design

### Three Limits

ccburn tracks three distinct usage limits (matching claude.ai Settings > Usage):

| Subcommand | Window | API Field | Description |
|------------|--------|-----------|-------------|
| `session` | 5-hour rolling | `five_hour` | "Current session" - blocks you immediately when hit |
| `weekly` | 7-day | `seven_day` | Weekly budget across all model types |
| `weekly-sonnet` | 7-day | `seven_day_sonnet` | Weekly budget for Sonnet-class models only |

Note: The API also returns `seven_day_opus` but this is less commonly a bottleneck. We track it in the database but don't display it prominently.

### TUI Layout

**No borders** - clean, minimal design like hwinfo-tui.

```
ccburn - Session (5h)                        Resets in 2h 14m

Usage        ████████████████████████░░░░░░░░░░░░░░░░  62%
Time Elapsed ██████████████████░░░░░░░░░░░░░░░░░░░░░░  45%

 100%│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
     │                                            ╭─────
  75%│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─╭───╯─ ─ ─ ─ ─
     │                                    ╭───╯  ╱
  50%│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─╭───╯─ ─ ╱─ ─ ─ ─ ─ ─
     │                            ╭───╯     ╱
  25%│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─╭───╯─ ─ ─ ─╱─ ─ ─ ─ ─ ─ ─ ─ ─
     │              ╭─────────╯        ╱   budget pace
   0%│──────────────╯                ╱
     └──────────────────────────────────────────────────────
      09:32      10:32      11:32      12:32      13:32   14:32
      (start)                                            (now)
```

### Key Layout Elements

1. **Header**: Tool name, selected limit name, reset countdown (single line)
   - Format: `ccburn - Session (5h)                        Resets in 2h 14m`
   - For weekly limits: `ccburn - Weekly                          Resets Tue 4:00 PM`
2. **Gauges (2 lines)**: Rich ProgressBar for the selected limit
   - **Usage** (green): Current utilization percentage
   - **Time Elapsed** (blue): Percentage of window that has passed (budget pace)
3. **Main Chart**: Burnup chart for the SELECTED limit only (fills remaining space)

### Header Reset Format

| Time until reset | Format | Example |
|------------------|--------|---------|
| < 24 hours | Relative | `Resets in 2h 14m` |
| >= 24 hours | Absolute | `Resets Tue 4:00 PM` |

### Progress Bar Colors

| Bar | Color | Description |
|-----|-------|-------------|
| Usage | Green (→Yellow→Red by threshold) | Actual utilization, color shifts at 50%/75%/90% |
| Time Elapsed | Blue | Budget pace - how much time has passed |

### Design Notes

- **No borders**: No box drawing characters around the UI
- **Minimal chrome**: Let the data speak for itself
- **Chart maximized**: Chart takes all remaining vertical space after gauges

### Chart X-Axis: Full Window Mode

The chart displays the **full limit window** from start to reset:

| Subcommand | X-Axis Span | Example |
|------------|-------------|---------|
| `session` | `resets_at - 5h` to `resets_at` | 09:32 to 14:32 |
| `weekly` | `resets_at - 7d` to `resets_at` | Jan 1 to Jan 8 |
| `weekly-sonnet` | `resets_at - 7d` to `resets_at` | Jan 1 to Jan 8 |

**Full window behavior**:
- Budget pace line: Always drawn as diagonal from (start, 0%) to (reset, 100%)
- Actual usage line: Progressively painted as data is collected
- For 7-day windows, chart will be mostly empty initially, filling in over time

**Optional `--since` flag**:
- `ccburn --since 2h` - Show only last 2 hours of data (zoomed view)
- `ccburn --since 24h` - Show only last 24 hours
- Default (no flag) = full window

### Limit Selection (Subcommands)

```bash
# Default: 5-hour session (most actionable)
ccburn

# Select specific limit via subcommand
ccburn session         # 5-hour rolling
ccburn weekly          # 7-day all models
ccburn weekly-sonnet   # 7-day sonnet

# Combine with time range
ccburn weekly --since 24h
```

No interactive switching - run with different subcommand to change view.

### Color Scheme

| Utilization | Color | Meaning |
|-------------|-------|---------|
| 0-50% | Green | Plenty available |
| 50-75% | Yellow | Monitor usage |
| 75-90% | Orange/Red | Slow down |
| 90-100% | Bright Red | Critical |

### Rich ProgressBar Implementation

Using `rich.progress.ProgressBar` for the gauge section:

```python
from rich.progress import ProgressBar
from rich.table import Table
from rich.style import Style

def create_gauge_section(limit_data: LimitData, budget_pace: float) -> Table:
    """Create the 2-bar gauge section for a limit."""
    table = Table.grid(padding=(0, 1))
    table.add_column(width=14)  # Label
    table.add_column(ratio=1)   # Bar
    table.add_column(width=8)   # Value

    # Usage bar - color by threshold
    usage_color = get_utilization_color(limit_data.utilization)
    usage_bar = ProgressBar(
        total=100,
        completed=limit_data.utilization * 100,
        style=Style(color=usage_color),
        complete_style=Style(color=usage_color),
        pulse=False,
    )
    table.add_row("Usage", usage_bar, f"{limit_data.utilization*100:.0f}%")

    # Time Elapsed bar - always blue
    elapsed_bar = ProgressBar(
        total=100,
        completed=budget_pace * 100,
        style=Style(color="blue"),
        complete_style=Style(color="blue"),
    )
    table.add_row("Time Elapsed", elapsed_bar, f"{budget_pace*100:.0f}%")

    return table
```

### Chart Components

Following Grafana burnup pattern:
- **Solid line (green/yellow/red)**: Actual utilization over time
- **Dashed line (dim)**: Budget pace reference (linear from 0% to 100% over window)
- **Horizontal line at 100%**: Limit ceiling (red)
- **Optional threshold at 75%**: Warning level (yellow, dashed)

### Plotext Integration

Using PlotextMixin pattern from hwinfo-tui:

```python
class PlotextMixin:
    """Rich-compatible mixin for plotext charts."""

    def __rich_console__(self, console: Console, options: ConsoleOptions):
        # Build plotext chart
        plt.clear_figure()
        plt.plot(times, utilizations, label="Usage", color="green")
        plt.plot(times, budget_pace, label="Pace", color="yellow")
        plt.hline(100, color="red")

        plt.ylim(0, 105)
        plt.xlabel("Time")
        plt.ylabel("Usage %")
        plt.theme("dark")

        # Render to string and yield
        chart_str = plt.build()
        yield Text(chart_str)
```

### Responsive Layout

Following hwinfo-tui patterns:
- **Full mode**: Terminal width >= 80, height >= 20
- **Compact mode**: Smaller terminals get simplified single-line display
- **Table height**: Minimized (stats summary)
- **Chart height**: Maximized (primary visualization)

## Implementation Patterns (from hwinfo-tui)

### Import Fallback for PyInstaller

```python
try:
    from .data.usage_client import UsageClient  # Relative import
except ImportError:
    from ccburn.data.usage_client import UsageClient  # Absolute fallback
```

### Rich Live Loop

```python
class CCBurnApp:
    def __init__(self, interval: float = 30.0):
        self.interval = interval
        self.running = threading.Event()
        self.running.set()

    def run(self):
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        with Live(self.layout, refresh_per_second=1) as live:
            while self.running.is_set():
                if self._should_refresh():
                    self._fetch_and_update()
                self.layout.update()
                live.update(self.layout)
                time.sleep(0.1)

    def _handle_signal(self, signum, frame):
        self.running.clear()
```

### Deterministic Color Assignment

```python
COLORS = ["green", "yellow", "orange", "red"]

def get_utilization_color(utilization: float) -> str:
    """Get color based on utilization percentage."""
    if utilization < 0.5:
        return "green"
    elif utilization < 0.75:
        return "yellow"
    elif utilization < 0.9:
        return "orange"
    else:
        return "red"
```

### Value Formatting

```python
def format_duration(minutes: int) -> str:
    """Format minutes as human-readable duration."""
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    mins = minutes % 60
    if hours < 24:
        return f"{hours}h {mins}m" if mins else f"{hours}h"
    days = hours // 24
    hours = hours % 24
    return f"{days}d {hours}h"

def format_percentage(value: float) -> str:
    """Format 0-1 float as percentage string."""
    return f"{value * 100:.0f}%"
```

## Performance Targets

Following hwinfo-tui standards:
- **Memory**: < 30MB baseline (simpler than hwinfo-tui)
- **CPU overhead**: < 1% of one core during normal operation
- **Startup**: < 1s to first display (after initial API call)
- **API polling**: Every 30-60 seconds (configurable)
- **Display refresh**: 1 second cadence for clock/countdown updates
- **SQLite operations**: < 10ms for read/write

## Error Handling

### Graceful Degradation

- **No credentials**: Exit with clear message about Claude Code login
- **API errors**: Show stale data from history with warning banner
- **Empty history**: Show current snapshot only, no chart
- **SQLite errors**: Fall back to in-memory operation

### Recovery Mechanisms

- **Exponential backoff**: For API retry (1s, 2s, 4s, max 3 attempts)
- **Stale data indicator**: Show "Last updated: X minutes ago" when using cached data
- **Graceful shutdown**: Clean SQLite close on SIGINT/SIGTERM

## Packaging and Distribution

### pyproject.toml

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "ccburn"
version = "1.0.0"
description = "Terminal-based Claude Code usage limit visualizer"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.8"
authors = [
    {name = "Your Name", email = "you@example.com"}
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Utilities",
]
dependencies = [
    "typer[all]>=0.9.0",
    "rich>=13.0.0",
    "plotext>=5.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]

[project.scripts]
ccburn = "ccburn.main:app"

[project.urls]
Homepage = "https://github.com/username/ccburn"
Repository = "https://github.com/username/ccburn"
Issues = "https://github.com/username/ccburn/issues"

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 100
target-version = "py38"

[tool.mypy]
python_version = "3.8"
strict = true
```

### CI/CD (GitHub Actions)

Following hwinfo-tui patterns:
- **ci.yml**: Matrix testing on Python 3.8-3.12, lint (ruff), typecheck (mypy), test (pytest)
- **release.yml**: Triggered on `v*` tags, builds sdist/wheel, publishes to PyPI

## Testing Strategy

### Unit Tests

- `test_calculator.py`: Budget pace, burn rate, time-to-empty, trend classification
- `test_history.py`: SQLite CRUD, retention policy, timestamp handling
- `test_usage_client.py`: API response parsing, error handling (with mocked responses)
- `test_formatting.py`: Duration formatting, percentage formatting

### Integration Tests

- `test_cli.py`: Typer CliRunner tests for all commands
- `test_app.py`: Full app lifecycle with mocked API

### Test Data

Mock API responses in `tests/fixtures/`:
```json
{
  "five_hour": {"utilization": 0.62, "resets_at": "2026-01-08T16:46:00Z"},
  "seven_day": {"utilization": 0.42, "resets_at": "2026-01-12T00:00:00Z"}
}
```

## Open Questions (Resolved)

1. **Token refresh**: ccburn will NOT attempt to refresh tokens. If expired, prompt user to restart Claude Code.
2. **History sharing**: SQLite schema is ccburn-specific. No compatibility requirement with other tools.
3. **Windows support**: Use `pathlib.Path` for all paths. SQLite and Rich work cross-platform.
4. **CLI framework**: Use Typer (not argparse) for consistency with hwinfo-tui.

## Validation Methodology

### Screenshot Capture Pipeline

Since the implementer (Claude) cannot directly view terminal output, validation uses Rich's built-in recording capability:

```python
from rich.console import Console
import cairosvg

def capture_screenshot(renderable, filename: str, width: int = 100) -> None:
    """Capture a Rich renderable as a PNG screenshot."""
    console = Console(record=True, width=width, force_terminal=True)
    console.print(renderable)
    svg = console.export_svg(title="ccburn")
    cairosvg.svg2png(bytestring=svg.encode(), write_to=filename, scale=2)
```

**Dependencies** (dev only):
- `cairosvg` - SVG to PNG conversion

**Workflow**:
1. Render TUI component to Rich Console with `record=True`
2. Export to SVG via `console.export_svg()`
3. Convert to PNG via `cairosvg.svg2png()`
4. Read PNG to visually verify output

### What Can Be Validated Programmatically

| Component | Validation Method |
|-----------|-------------------|
| JSON output structure | Parse and assert fields |
| Compact output format | String matching |
| Calculator logic | Unit tests with known inputs |
| API response parsing | Mock responses + assertions |
| SQLite operations | In-memory DB tests |
| Exit codes | CLI runner tests |

### What Requires Visual Inspection

| Component | Validation Method |
|-----------|-------------------|
| Progress bar appearance | Screenshot capture → visual check |
| Chart rendering | Screenshot capture → visual check |
| Color thresholds | Screenshot capture → visual check |
| Layout responsiveness | Screenshot at different widths |
| Overall TUI aesthetics | Screenshot capture → visual check |

## Acceptance Criteria (Definition of Done)

### Core Functionality

- [x] `ccburn --version` shows version from pyproject.toml
- [x] `ccburn --help` shows help with all subcommands and flags
- [x] `ccburn` (no args) launches TUI showing session (5h) limit
- [x] `ccburn session` shows 5-hour rolling limit
- [x] `ccburn weekly` shows 7-day all models limit
- [x] `ccburn weekly-sonnet` shows 7-day sonnet limit

### Output Modes

- [x] `ccburn --json` outputs valid JSON matching spec format
- [x] `ccburn --once` prints single snapshot and exits (exit code 0)
- [x] `ccburn --compact` outputs single-line format for status bars
- [x] `ccburn --json --once` combines correctly

### Data Pipeline

- [x] Reads OAuth token from `~/.claude/.credentials.json`
- [x] Calls Usage API with correct headers
- [x] Parses API response into UsageSnapshot
- [x] Stores snapshots in SQLite (`~/.ccburn/history.db`)
- [x] Retrieves historical snapshots for chart
- [x] Auto-prunes data older than 7 days

### TUI Visual Requirements

- [x] Header shows limit name and reset countdown
- [x] Usage progress bar shows utilization with correct color thresholds
- [x] Time Elapsed progress bar shows budget pace in blue
- [x] Burnup chart renders with plotext
- [x] Chart shows actual usage line (solid, colored by threshold)
- [x] Chart shows budget pace line (dashed/dim)
- [x] Chart X-axis spans full window (5h or 7d depending on limit)
- [x] No borders around UI elements (minimal chrome)

### Calculator Logic

- [x] Budget pace calculated correctly: `(now - window_start) / window_duration`
- [x] Burn rate calculated from recent snapshots (% per hour)
- [x] Time-to-empty prediction calculated when burn rate > 0
- [x] Trend classification matches thresholds (low/moderate/high/critical)
- [x] Status classification (ahead_of_pace/on_pace/behind_pace) correct

### Error Handling

- [x] Missing credentials file → helpful error message, exit code 1
- [x] Expired token → prompt to restart Claude Code, exit code 1
- [x] API error → warning banner, continue with stale data
- [x] Network error → retry with backoff, then warning
- [x] SQLite error → fall back to in-memory operation
- [x] Ctrl+C → graceful shutdown, exit code 0

### Performance

- [x] Startup < 1s to first display
- [x] Memory < 30MB baseline
- [x] API polling interval configurable (default 30s)
- [x] Display refresh ~1s for countdown updates

### Screenshot Validation Checkpoints

Generate and verify screenshots at these milestones:

1. **Progress bars only** - Two bars (Usage green, Time Elapsed blue) render correctly
2. **Header + bars** - Header with limit name and reset countdown
3. **Chart only** - Plotext burnup chart with mock data
4. **Full TUI** - Complete layout assembled
5. **Color thresholds** - Screenshots at 25%, 50%, 75%, 95% utilization
6. **Compact output** - Single-line format renders correctly

### Final Validation

When all above criteria pass:
1. Run `ccburn` with real credentials
2. Capture screenshot of live TUI
3. Compare visual appearance to spec mockup (section: TUI Layout)
4. User confirms TUI looks as expected

## Future Considerations (Not MVP)

1. **MCP Server** - Let Claude query usage directly without Bash
2. **Notifications** - Desktop alerts at 80%, 95%
3. **tmux integration** - Status bar plugin
4. **Multi-account** - Support for team accounts
5. **Historical trends** - Week-over-week comparison

---

*Spec version: 1.1*
*Created: January 8, 2026*
*Updated: January 8, 2026 - Added validation methodology and acceptance criteria*
*Based on: hwinfo-tui architecture, Grafana burnup dashboard, claude-usage-exporter.py*
