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
    help="Time window to display (e.g., '2h', '24h', '7d', 'start'). Default: full window.",
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

PollIntervalOption = typer.Option(
    60,
    "--poll-interval",
    "-p",
    help="API poll interval in seconds (default: 60). Display refreshes at --interval.",
    min=5,
    max=3600,
)

DebugOption = typer.Option(
    False,
    "--debug",
    "-d",
    help="Show debug information including raw API response.",
)

RecentWindowOption = typer.Option(
    None,
    "--recent-window",
    "-r",
    help="Limit burn rate calculation to recent data (e.g. '30m', '1h'). Useful after idle periods.",
)


def run_app(
    limit_type: LimitType | None,
    json_output: bool = False,
    once: bool = False,
    compact: bool = False,
    since: str | None = None,
    until: str = "now",
    interval: int = 5,
    poll_interval: int = 60,
    debug: bool = False,
    recent_window: str | None = None,
) -> None:
    """Run the ccburn application with the specified options."""
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
    # 'start' means beginning of the window — uses timedelta(0) as a sentinel
    # so the chart knows --since was explicitly set (enables --until cropping)
    since_duration = None
    if since and since.lower() == "start":
        since_duration = timedelta(0)
    elif since:
        try:
            since_duration = parse_duration(since)
        except typer.BadParameter as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1) from None

    recent_window_minutes = None
    if recent_window:
        try:
            recent_window_minutes = int(parse_duration(recent_window).total_seconds() / 60)
        except typer.BadParameter as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1) from None

    app = CCBurnApp(
        limit_type=limit_type,
        interval=interval,
        poll_interval=poll_interval,
        since_duration=since_duration,
        until=until,
        json_output=json_output,
        once=once,
        compact=compact,
        debug=debug,
        recent_window_minutes=recent_window_minutes,
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
        poll_interval: int = PollIntervalOption,
        debug: bool = DebugOption,
        recent_window: str | None = RecentWindowOption,
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
            poll_interval=poll_interval,
            debug=debug,
            recent_window=recent_window,
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
        poll_interval: int = PollIntervalOption,
        debug: bool = DebugOption,
        recent_window: str | None = RecentWindowOption,
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
            poll_interval=poll_interval,
            debug=debug,
            recent_window=recent_window,
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
        poll_interval: int = PollIntervalOption,
        debug: bool = DebugOption,
        recent_window: str | None = RecentWindowOption,
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
            poll_interval=poll_interval,
            debug=debug,
            recent_window=recent_window,
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
        poll_interval: int = PollIntervalOption,
        debug: bool = DebugOption,
        recent_window: str | None = RecentWindowOption,
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
            poll_interval=poll_interval,
            debug=debug,
            recent_window=recent_window,
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


def create_collect_command(app: typer.Typer) -> None:
    """Create the collect subcommand."""

    @app.command()
    def collect() -> None:
        """Collect rate_limits from Claude Code statusline JSON.

        Reads statusline JSON from stdin, extracts rate_limits data,
        writes it to the history DB, and passes stdin through to stdout.
        Designed to wrap your existing statusline command:

        \b
        Usage in ~/.claude/settings.json:
            "statusLine": {
                "command": "ccburn collect | your-statusline-command"
            }
        """
        # Delegate to the fast standalone module (avoids double Typer overhead)
        try:
            from .collect import main as collect_main
        except ImportError:
            from ccburn.collect import main as collect_main

        collect_main()
        raise typer.Exit(0)


def create_describe_command(app: typer.Typer) -> None:
    """Create the describe subcommand."""

    @app.command()
    def describe() -> None:
        """Describe ccburn for AI agents: what it does, how to set it up.

        Outputs a structured description that an AI agent can use to
        understand ccburn and configure it automatically.
        """
        import json

        try:
            from importlib.metadata import version as get_version

            ver = get_version("ccburn")
        except Exception:
            ver = "unknown"

        try:
            from .data.credentials import get_ccburn_data_dir, get_claude_config_dir
        except ImportError:
            from ccburn.data.credentials import get_ccburn_data_dir, get_claude_config_dir

        claude_config = str(get_claude_config_dir())
        data_dir = str(get_ccburn_data_dir())
        settings_path = f"{claude_config}/settings.json"

        description = {
            "name": "ccburn",
            "version": ver,
            "summary": (
                "Terminal-based Claude Code usage limit visualizer. "
                "Displays real-time burn-up charts showing session and weekly "
                "usage against budget pace."
            ),
            "data_sources": {
                "description": (
                    "ccburn works out of the box — it fetches usage data via the OAuth API "
                    "and Claude Desktop cookies. However, the OAuth API has persistent rate "
                    "limiting (429 errors), so the recommended setup adds `ccburn collect` "
                    "to the Claude Code statusline to receive usage data directly from "
                    "Claude Code with zero API calls."
                ),
                "strategy_chain": [
                    "DB cache (from `ccburn collect` or previous fetches, up to 2 min old)",
                    "OAuth API (clean path, may hit 429 rate limit)",
                    "Claude Desktop web API via cookies + curl (default profile only)",
                    "SQLite history fallback (stale data with banner)",
                ],
            },
            "setup": {
                "description": (
                    "ccburn works without any setup, but for best results add `ccburn collect` "
                    "to the Claude Code statusline. This pipes Claude Code's statusline JSON "
                    "through `ccburn collect`, which extracts rate_limits data into a local "
                    "database. The original JSON is passed through to stdout unchanged, so "
                    "your existing statusline command continues to work."
                ),
                "step_1": {
                    "action": "Configure statusLine in Claude Code settings",
                    "file": settings_path,
                    "instructions": (
                        "In the statusLine.command field, prepend `ccburn collect |` "
                        "before the existing command. If no statusLine is configured, "
                        "set it to just `ccburn collect`."
                    ),
                    "example_existing": {
                        "before": "npx -y ccstatusline@latest",
                        "after": "ccburn collect | npx -y ccstatusline@latest",
                    },
                    "example_new": "ccburn collect",
                },
                "step_2": {
                    "action": "Restart Claude Code to pick up the new statusline command",
                },
                "step_3": {
                    "action": "Run ccburn in a separate terminal",
                    "command": "ccburn",
                    "notes": (
                        "ccburn auto-detects the best available data (session, weekly, "
                        "or monthly credits). Use `ccburn session`, `ccburn weekly`, or "
                        "`ccburn monthly` to display a specific limit."
                    ),
                },
                "multi_profile": {
                    "description": (
                        "For multiple Claude Code profiles, set CLAUDE_CONFIG_DIR before "
                        "running ccburn. Each profile gets its own isolated database."
                    ),
                    "example": "CLAUDE_CONFIG_DIR=~/.claude-personal ccburn",
                },
            },
            "how_collect_works": {
                "optional": True,
                "description": (
                    "`ccburn collect` is optional. Without it, ccburn fetches data itself "
                    "via OAuth API or Claude Desktop cookies. `collect` is recommended "
                    "for Pro/Max plans because it avoids API rate limits."
                ),
                "stdin": "Receives Claude Code statusline JSON (includes rate_limits since v2.1.80)",
                "stdout": "Passes the same JSON through unchanged (pipe-safe)",
                "side_effect": f"Writes usage snapshots to SQLite database at {data_dir}/history.db",
                "requires": "Claude Code >= 2.1.80 (for rate_limits in statusline JSON)",
                "limitation": (
                    "Enterprise accounts do NOT receive rate_limits in the statusline JSON. "
                    "Enterprise uses monthly credits (extra_usage) which is not included in "
                    "the statusline data. For enterprise, ccburn falls back to the OAuth API "
                    "or Claude Desktop cookies automatically."
                ),
            },
            "commands": {
                "ccburn": "Auto-detect and display best available limit (TUI)",
                "ccburn session": "Display 5-hour rolling session limit",
                "ccburn weekly": "Display 7-day weekly limit",
                "ccburn monthly": "Display monthly credit usage (enterprise)",
                "ccburn collect": "Pipe: read statusline JSON from stdin, save to DB, pass through",
                "ccburn describe": "Output this description (for AI agents)",
                "ccburn clear-history": "Clear all stored usage history",
            },
            "common_flags": {
                "--once": "Print once and exit (no live updates)",
                "--json": "Output JSON instead of TUI",
                "--compact": "Single-line output for status bars/tmux",
                "--debug": "Show debug information and strategy used",
                "--since": "Time window (e.g., '2h', '7d', 'start')",
                "--until": "Display end: 'now', 'end', or 'depleted'",
                "--interval": "Render interval in seconds (timers, chart refresh)",
                "--poll-interval": "API poll interval in seconds (default 60, display stays live between polls)",
            },
            "paths": {
                "claude_config_dir": claude_config,
                "ccburn_data_dir": data_dir,
                "settings_file": settings_path,
                "history_db": f"{data_dir}/history.db",
                "log_file": f"{data_dir}/ccburn.log",
            },
        }

        typer.echo(json.dumps(description, indent=2))
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
    create_collect_command(app)
    create_describe_command(app)
    create_clear_history_command(app)
