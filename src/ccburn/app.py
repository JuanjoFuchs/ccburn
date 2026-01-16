"""Main application class for ccburn."""

import os
import signal
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from rich.console import Console
from rich.live import Live

try:
    from .data.credentials import CredentialsNotFoundError, TokenExpiredError
    from .data.history import HistoryDB
    from .data.models import LimitType, UsageSnapshot
    from .data.usage_client import APIError, NetworkError, UsageClient
    from .display.gauges import create_compact_output, get_pace_emoji
    from .display.layout import BurnupLayout
    from .utils.calculator import calculate_budget_pace, calculate_burn_metrics
except ImportError:
    from ccburn.data.credentials import CredentialsNotFoundError, TokenExpiredError
    from ccburn.data.history import HistoryDB
    from ccburn.data.models import LimitType, UsageSnapshot
    from ccburn.data.usage_client import APIError, NetworkError, UsageClient
    from ccburn.display.gauges import create_compact_output, get_pace_emoji
    from ccburn.display.layout import BurnupLayout
    from ccburn.utils.calculator import calculate_budget_pace, calculate_burn_metrics


class CCBurnApp:
    """Main application class for ccburn."""

    def __init__(
        self,
        limit_type: LimitType = LimitType.SESSION,
        interval: int = 5,
        since_duration: timedelta | None = None,
        json_output: bool = False,
        once: bool = False,
        compact: bool = False,
        debug: bool = False,
    ):
        """Initialize the application.

        Args:
            limit_type: Which limit to display
            interval: Refresh interval in seconds
            since_duration: Time window duration for zoom view (sliding window)
            json_output: Output JSON instead of TUI
            once: Print once and exit
            compact: Single-line output for status bars
            debug: Show debug information
        """
        self.limit_type = limit_type
        self.interval = interval
        self.since_duration = since_duration
        self.json_output = json_output
        self.once = once
        self.compact = compact
        self.debug = debug

        # Disable legacy_windows mode for modern terminals to prevent Unicode issues
        # Rich may incorrectly detect legacy mode even in Windows Terminal
        use_legacy = None  # Auto-detect by default
        if os.environ.get("WT_SESSION"):  # Windows Terminal
            use_legacy = False
        self.console = Console(legacy_windows=use_legacy)
        self.client = UsageClient()
        self.history: HistoryDB | None = None
        self.layout = BurnupLayout(self.console)

        # State
        self.running = threading.Event()
        self.last_snapshot: UsageSnapshot | None = None
        self.last_fetch_time: datetime | None = None
        self.last_error: str | None = None
        self.snapshots: list[UsageSnapshot] = []

    def _get_since_datetime(self) -> datetime | None:
        """Calculate the since datetime based on current time and duration.

        Returns:
            datetime for filtering, or None if no duration set
        """
        if self.since_duration is None:
            return None
        return datetime.now(timezone.utc) - self.since_duration

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum: int, frame: Any) -> None:
            self.stop()

        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, signal_handler)

    def _initialize(self) -> bool:
        """Initialize resources.

        Returns:
            True if initialization succeeded
        """
        try:
            # Initialize history database
            try:
                self.history = HistoryDB()
                # Prune old data on startup
                self.history.prune_old_data()
                # Load existing snapshots (use current since datetime)
                self.snapshots = self.history.get_snapshots_for_limit(
                    self.limit_type,
                    since=self._get_since_datetime(),
                )
            except Exception as e:
                # Fall back to in-memory if SQLite fails
                self.console.print(
                    f"[yellow]Warning: Using in-memory storage ({e})[/yellow]"
                )
                self.history = HistoryDB(in_memory=True)
                self.snapshots = []

            return True

        except Exception as e:
            self.console.print(f"[red]Initialization failed: {e}[/red]")
            return False

    def _fetch_and_update(self) -> bool:
        """Fetch new data and update state.

        Uses shared database as cache - if another instance recently fetched,
        use that data instead of hitting the API again.

        Returns:
            True if fetch succeeded
        """
        try:
            snapshot = None

            # Check if fresh data exists in database (from another instance)
            if self.history:
                age = self.history.get_latest_snapshot_age_seconds()
                # If data is fresh (less than half our interval), use cached data
                if age is not None and age < (self.interval / 2):
                    snapshot = self.history.get_latest_snapshot()
                    if snapshot:
                        self.last_snapshot = snapshot
                        self.last_fetch_time = snapshot.timestamp
                        self.last_error = None
                        # Reload snapshots from database (use current since datetime)
                        self.snapshots = self.history.get_snapshots_for_limit(
                            self.limit_type,
                            since=self._get_since_datetime(),
                        )
                        return True

            # No fresh cached data, fetch from API
            snapshot = self.client.fetch_usage()
            self.last_snapshot = snapshot
            self.last_fetch_time = datetime.now(timezone.utc)
            self.last_error = None

            # Save to history
            if self.history:
                self.history.save_snapshot(snapshot)

            # Add to local list
            self.snapshots.append(snapshot)

            # Keep only relevant snapshots (based on since_duration or window)
            since_dt = self._get_since_datetime()
            if since_dt:
                self.snapshots = [s for s in self.snapshots if s.timestamp >= since_dt]
            else:
                # Keep last 24 hours of data for calculations
                cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
                self.snapshots = [s for s in self.snapshots if s.timestamp >= cutoff]

            return True

        except CredentialsNotFoundError as e:
            self.console.print(f"[red]{e}[/red]")
            return False

        except TokenExpiredError as e:
            self.console.print(f"[red]{e}[/red]")
            return False

        except (APIError, NetworkError) as e:
            self.last_error = str(e)
            return False

        except Exception as e:
            self.last_error = f"Unexpected error: {e}"
            return False

    def _should_refresh(self) -> bool:
        """Check if we should fetch new data.

        Returns:
            True if it's time to refresh
        """
        if self.last_fetch_time is None:
            return True

        elapsed = (datetime.now(timezone.utc) - self.last_fetch_time).total_seconds()
        return elapsed >= self.interval

    def run(self) -> int:
        """Run the application.

        Returns:
            Exit code (0 for success, 1 for error)
        """
        # Show loading message for TUI mode
        if not self.json_output and not self.compact and not self.once:
            self.console.print("[dim]🔥 Loading ccburn...[/dim]", end="\r")

        if not self._initialize():
            return 1

        # Initial fetch
        if not self._fetch_and_update():
            if self.last_snapshot is None:
                # No cached data available - error should have been printed in _fetch_and_update
                self.console.print("[red]Failed to fetch usage data. Check your credentials.[/red]")
                return 1

        # Handle different output modes
        if self.json_output:
            return self._run_json()
        elif self.compact:
            return self._run_compact()
        elif self.once:
            return self._run_once()
        else:
            return self._run_tui()

    def _run_json(self) -> int:
        """Run in JSON output mode.

        Returns:
            Exit code
        """
        output = self._create_json_output()
        self.console.print_json(data=output)
        return 0

    def _run_compact(self) -> int:
        """Run in compact single-line mode.

        Returns:
            Exit code
        """
        if self.last_snapshot is None:
            self.console.print("No data available")
            return 1

        budget_pace = 0.0
        if self.last_snapshot.session:
            budget_pace = calculate_budget_pace(
                self.last_snapshot.session.resets_at,
                self.last_snapshot.session.window_hours,
            )

        output = create_compact_output(
            self.last_snapshot.session,
            self.last_snapshot.weekly,
            self.last_snapshot.weekly_sonnet,
            budget_pace,
        )
        self.console.print(output)
        return 0

    def _run_once(self) -> int:
        """Run once and exit (no live updates).

        Returns:
            Exit code
        """
        if self.last_snapshot is None:
            self.console.print("[red]No data available[/red]")
            return 1

        limit_data = self.last_snapshot.get_limit(self.limit_type)

        # Create and print the layout
        layout = self.layout.update(
            self.limit_type,
            limit_data,
            self.snapshots,
            error=self.last_error,
            since_duration=self.since_duration,
        )
        self.console.print(layout)

        # Show debug info if requested
        if self.debug and self.client.get_last_response():
            self.console.print("\n[dim]Raw API Response:[/dim]")
            self.console.print_json(data=self.client.get_last_response())

        return 0

    def _run_tui(self) -> int:
        """Run the live TUI.

        Returns:
            Exit code
        """
        self._setup_signal_handlers()
        self.running.set()

        try:
            # Create initial display
            limit_data = None
            if self.last_snapshot:
                limit_data = self.last_snapshot.get_limit(self.limit_type)

            initial_layout = self.layout.update(
                self.limit_type,
                limit_data,
                self.snapshots,
                error=self.last_error,
                since_duration=self.since_duration,
            )

            # Set initial window title
            self._update_window_title()

            with Live(
                initial_layout,
                console=self.console,
                refresh_per_second=1,
                transient=False,
                screen=True,
                vertical_overflow="visible",
            ) as live:
                self._main_loop(live)

            return 0

        except KeyboardInterrupt:
            return 0

        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return 1

        finally:
            self._cleanup()

    def _main_loop(self, live: Live) -> None:
        """Main TUI loop.

        Args:
            live: Rich Live instance
        """
        last_update = 0.0

        while self.running.is_set():
            try:
                current_time = time.time()

                # Check if we should refresh data
                if self._should_refresh():
                    self._fetch_and_update()

                # Update display
                if current_time - last_update >= 1.0:  # Update display every second
                    limit_data = None
                    if self.last_snapshot:
                        limit_data = self.last_snapshot.get_limit(self.limit_type)

                    stale_since = None
                    if self.last_error and self.last_fetch_time:
                        stale_since = self.last_fetch_time

                    updated_layout = self.layout.update(
                        self.limit_type,
                        limit_data,
                        self.snapshots,
                        error=self.last_error,
                        stale_since=stale_since,
                        since_duration=self.since_duration,
                    )
                    live.update(updated_layout)
                    self._update_window_title()
                    last_update = current_time

                # Small sleep to prevent busy waiting
                time.sleep(0.05)

            except Exception:
                # Log but continue
                time.sleep(0.5)

    def _create_json_output(self) -> dict:
        """Create JSON output structure.

        Returns:
            Dictionary matching the spec JSON format
        """
        output: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "limits": {},
            "burn_rate": None,
            "recommendation": None,
        }

        if self.last_snapshot is None:
            return output

        # Add all limits
        for lt in [LimitType.SESSION, LimitType.WEEKLY, LimitType.WEEKLY_SONNET]:
            limit_data = self.last_snapshot.get_limit(lt)
            if limit_data:
                metrics = calculate_burn_metrics(limit_data, self.snapshots)
                minutes_left = int(
                    (limit_data.resets_at - datetime.now(timezone.utc)).total_seconds() / 60
                )
                hours_left = minutes_left / 60

                output["limits"][lt.value] = {
                    "utilization": limit_data.utilization,
                    "budget_pace": metrics.budget_pace,
                    "resets_at": limit_data.resets_at.isoformat(),
                    "resets_in_minutes": minutes_left if lt == LimitType.SESSION else None,
                    "resets_in_hours": hours_left if lt != LimitType.SESSION else None,
                    "window_hours": limit_data.window_hours,
                    "status": metrics.status,
                }

        # Add burn rate and projection for selected limit
        limit_data = self.last_snapshot.get_limit(self.limit_type)
        if limit_data:
            metrics = calculate_burn_metrics(limit_data, self.snapshots)
            output["burn_rate"] = {
                "limit": self.limit_type.value,
                "percent_per_hour": round(metrics.percent_per_hour, 2),
                "trend": metrics.trend,
                "estimated_minutes_to_100": metrics.estimated_minutes_to_100,
            }
            output["recommendation"] = metrics.recommendation

            # Add projection data
            if metrics.percent_per_hour > 0:
                current_pct = limit_data.utilization * 100
                remaining_pct = 100.0 - current_pct
                hours_to_100 = remaining_pct / metrics.percent_per_hour

                now = datetime.now(timezone.utc)
                remaining_window_hours = (limit_data.resets_at - now).total_seconds() / 3600

                if hours_to_100 <= remaining_window_hours:
                    # Will hit 100% before window ends
                    projected_end_pct = 100.0
                    hits_100 = True
                    status = "warning"
                else:
                    # Won't hit 100%
                    projected_end_pct = current_pct + (metrics.percent_per_hour * remaining_window_hours)
                    hits_100 = False
                    status = "safe"

                output["projection"] = {
                    "available": True,
                    "projected_end_pct": round(min(projected_end_pct, 100.0), 1),
                    "hits_100": hits_100,
                    "hours_to_100": round(hours_to_100, 1) if hits_100 else None,
                    "status": status,
                }
            else:
                output["projection"] = {
                    "available": False,
                    "reason": "insufficient_data" if metrics.percent_per_hour == 0 else "usage_decreasing",
                }

        return output

    def stop(self) -> None:
        """Stop the application."""
        self.running.clear()

    def _update_window_title(self) -> None:
        """Update terminal window title with current status."""
        if self.last_snapshot is None:
            self.console.set_window_title("ccburn")
            return

        limit_data = self.last_snapshot.get_limit(self.limit_type)
        if limit_data is None:
            self.console.set_window_title("ccburn")
            return

        # Calculate pace and get emoji
        budget_pace = calculate_budget_pace(
            limit_data.resets_at,
            limit_data.window_hours,
        )
        emoji = get_pace_emoji(limit_data.utilization, budget_pace)
        percent = int(limit_data.utilization * 100)

        # Format: 🔥 45% - ccburn Session
        title = f"{emoji} {percent}% - ccburn {self.limit_type.display_name}"
        self.console.set_window_title(title)

    def _cleanup(self) -> None:
        """Clean up resources."""
        # Reset window title
        self.console.set_window_title("")
        if self.history:
            self.history.close()
