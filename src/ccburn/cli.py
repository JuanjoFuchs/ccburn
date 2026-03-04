"""CLI command definitions for ccburn."""

import re
from datetime import timedelta

import typer
from rich.console import Console

try:
    from .data.models import LimitType
except ImportError:
    from ccburn.data.models import LimitType


def parse_duration(value: str) -> timedelta:
    """Parse duration string like '2h', '30m', '1d', '24h'.

    Args:
        value: Duration string

    Returns:
        timedelta object

    Raises:
        typer.BadParameter: If format is invalid
    """
    match = re.match(r"^(\d+)([mhdw])$", value.lower())
    if not match:
        raise typer.BadParameter(
            f"Invalid duration format: {value}. Use format like '2h', '30m', '1d', '1w'."
        )

    amount = int(match.group(1))
    unit = match.group(2)

    if unit == "m":
        return timedelta(minutes=amount)
    elif unit == "h":
        return timedelta(hours=amount)
    elif unit == "d":
        return timedelta(days=amount)
    elif unit == "w":
        return timedelta(weeks=amount)

    raise typer.BadParameter(f"Unknown time unit: {unit}")


def duration_callback(value: str | None) -> str | None:
    """Typer callback for parsing duration strings."""
    if value is None:
        return None
    return parse_duration(value)


# Common options used by all subcommands
JsonOption = typer.Option(
    False,
    "--json",
    "-j",
    help="Output JSON instead of TUI.",
)

OnceOption = typer.Option(
    False,
    "--once",
    "-1",
    help="Print once and exit (no live updates).",
)

CompactOption = typer.Option(
    False,
    "--compact",
    "-c",
    help="Single-line output for status bars/tmux.",
)

SinceOption = typer.Option(
    None,
    "--since",
    "-s",
    help="Time window to display (e.g., '2h', '24h', '7d'). Default: full window.",
)

UntilOption = typer.Option(
    "now",
    "--until",
    "-u",
    help="Display end: 'now' (default), 'end' (window end), or 'depleted' (projected depletion).",
)

SessionIntervalOption = typer.Option(
    5,
    "--interval",
    "-i",
    help="Refresh interval in seconds (default: 5 for session).",
    min=1,
    max=300,
)

WeeklyIntervalOption = typer.Option(
    30,
    "--interval",
    "-i",
    help="Refresh interval in seconds (default: 30 for weekly).",
    min=1,
    max=300,
)

MonthlyIntervalOption = typer.Option(
    60,
    "--interval",
    "-i",
    help="Refresh interval in seconds (default: 60 for monthly).",
    min=1,
    max=300,
)

DebugOption = typer.Option(
    False,
    "--debug",
    "-d",
    help="Show debug information including raw API response.",
)


def run_app(
    limit_type: LimitType | None,
    json_output: bool = False,
    once: bool = False,
    compact: bool = False,
    since: str | None = None,
    until: str = "now",
    interval: int = 5,
    debug: bool = False,
) -> None:
    """Run the ccburn application with the specified options.

    Args:
        limit_type: Which limit to display
        json_output: Output JSON instead of TUI
        once: Print once and exit
        compact: Single-line output
        since: Time window string (e.g., '2h', '24h')
        until: Display end: 'now' or 'end'
        interval: Refresh interval in seconds
        debug: Show debug info
    """
    try:
        from .app import CCBurnApp
    except ImportError:
        from ccburn.app import CCBurnApp

    # Validate --until requires --since
    if until != "now" and not since:
        typer.echo("Error: --until requires --since to be set.", err=True)
        raise typer.Exit(1)

    # Validate --until value
    if until not in ("now", "end", "depleted"):
        typer.echo(f"Error: --until must be 'now', 'end', or 'depleted', got '{until}'.", err=True)
        raise typer.Exit(1)

    # Parse since duration if provided
    since_duration = None
    if since:
        try:
            since_duration = parse_duration(since)
        except typer.BadParameter as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1) from None

    app = CCBurnApp(
        limit_type=limit_type,
        interval=interval,
        since_duration=since_duration,
        until=until,
        json_output=json_output,
        once=once,
        compact=compact,
        debug=debug,
    )

    exit_code = app.run()
    raise typer.Exit(exit_code)


def create_session_command(app: typer.Typer) -> None:
    """Create the session subcommand."""

    @app.command()
    def session(
        json_output: bool = JsonOption,
        once: bool = OnceOption,
        compact: bool = CompactOption,
        since: str | None = SinceOption,
        until: str = UntilOption,
        interval: int = SessionIntervalOption,
        debug: bool = DebugOption,
    ) -> None:
        """Display 5-hour rolling session limit.

        This is the default limit that blocks you immediately when exceeded.
        """
        run_app(
            LimitType.SESSION,
            json_output=json_output,
            once=once,
            compact=compact,
            since=since,
            until=until,
            interval=interval,
            debug=debug,
        )


def create_weekly_command(app: typer.Typer) -> None:
    """Create the weekly subcommand."""

    @app.command()
    def weekly(
        json_output: bool = JsonOption,
        once: bool = OnceOption,
        compact: bool = CompactOption,
        since: str | None = SinceOption,
        until: str = UntilOption,
        interval: int = WeeklyIntervalOption,
        debug: bool = DebugOption,
    ) -> None:
        """Display 7-day weekly limit (all models).

        Shows your weekly budget across all model types.
        """
        run_app(
            LimitType.WEEKLY,
            json_output=json_output,
            once=once,
            compact=compact,
            since=since,
            until=until,
            interval=interval,
            debug=debug,
        )


def create_weekly_sonnet_command(app: typer.Typer) -> None:
    """Create the weekly-sonnet subcommand."""

    @app.command("weekly-sonnet")
    def weekly_sonnet(
        json_output: bool = JsonOption,
        once: bool = OnceOption,
        compact: bool = CompactOption,
        since: str | None = SinceOption,
        until: str = UntilOption,
        interval: int = WeeklyIntervalOption,
        debug: bool = DebugOption,
    ) -> None:
        """Display 7-day weekly limit (Sonnet only).

        Shows your weekly Sonnet-class model budget.
        """
        run_app(
            LimitType.WEEKLY_SONNET,
            json_output=json_output,
            once=once,
            compact=compact,
            since=since,
            until=until,
            interval=interval,
            debug=debug,
        )


def create_monthly_command(app: typer.Typer) -> None:
    """Create the monthly subcommand."""

    @app.command()
    def monthly(
        json_output: bool = JsonOption,
        once: bool = OnceOption,
        compact: bool = CompactOption,
        since: str | None = SinceOption,
        until: str = UntilOption,
        interval: int = MonthlyIntervalOption,
        debug: bool = DebugOption,
    ) -> None:
        """Display monthly credit usage (enterprise accounts).

        Shows your monthly credit budget and current usage.
        Resets on the 1st of each month.
        """
        run_app(
            LimitType.MONTHLY,
            json_output=json_output,
            once=once,
            compact=compact,
            since=since,
            until=until,
            interval=interval,
            debug=debug,
        )


def create_clear_history_command(app: typer.Typer) -> None:
    """Create the clear-history command."""

    @app.command("clear-history")
    def clear_history(
        force: bool = typer.Option(
            False,
            "--force",
            "-f",
            help="Skip confirmation prompt.",
        ),
    ) -> None:
        """Clear all stored usage history.

        This removes all snapshots from the SQLite database at ~/.ccburn/history.db
        """
        console = Console()

        if not force:
            confirm = typer.confirm("Are you sure you want to clear all history?")
            if not confirm:
                console.print("[yellow]Cancelled.[/yellow]")
                raise typer.Exit(0)

        try:
            from .data.history import HistoryDB
        except ImportError:
            from ccburn.data.history import HistoryDB

        with HistoryDB() as db:
            count = db.clear_history()
            console.print(f"[green]Cleared {count} snapshots from history.[/green]")

        raise typer.Exit(0)


def register_commands(app: typer.Typer) -> None:
    """Register all subcommands with the Typer app.

    Args:
        app: Typer application instance
    """
    create_session_command(app)
    create_weekly_command(app)
    create_weekly_sonnet_command(app)
    create_monthly_command(app)
    create_clear_history_command(app)
