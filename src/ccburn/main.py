"""ccburn - Terminal-based Claude Code usage limit visualizer."""


import typer
from rich.console import Console

try:
    from .cli import (
        CompactOption,
        DebugOption,
        JsonOption,
        OnceOption,
        SessionIntervalOption,
        SinceOption,
        register_commands,
        run_app,
    )
    from .data.models import LimitType
    from .data.usage_client import UsageClient
except ImportError:
    from ccburn.cli import (
        CompactOption,
        DebugOption,
        JsonOption,
        OnceOption,
        SessionIntervalOption,
        SinceOption,
        register_commands,
        run_app,
    )
    from ccburn.data.models import LimitType
    from ccburn.data.usage_client import UsageClient


def auto_detect_limit_type() -> LimitType | None:
    """Auto-detect which limit type to use based on available data.

    Priority: session -> monthly -> weekly

    Returns:
        Best available LimitType, or None if no data available.
    """
    try:
        client = UsageClient()
        snapshot = client.fetch_usage()

        if snapshot.session is not None:
            return LimitType.SESSION
        if snapshot.monthly is not None:
            return LimitType.MONTHLY
        if snapshot.weekly is not None:
            return LimitType.WEEKLY

        return None
    except Exception:
        return None


app = typer.Typer(
    name="ccburn",
    help="Visualize Claude Code usage limits with real-time burn-up charts.",
    rich_markup_mode="rich",
    add_completion=True,
    no_args_is_help=False,
)

# Register subcommands
register_commands(app)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
    ),
    json_output: bool = JsonOption,
    once: bool = OnceOption,
    compact: bool = CompactOption,
    since: str | None = SinceOption,
    interval: int = SessionIntervalOption,
    debug: bool = DebugOption,
) -> None:
    """ccburn - Claude Code usage limit visualizer.

    Visualize your Claude Code usage limits with real-time burn-up charts.
    Auto-detects available data (session or monthly credits).

    \b
    Examples:
        ccburn              # Auto-detect best available data
        ccburn session      # Explicit: 5-hour rolling session limit
        ccburn weekly       # Explicit: 7-day weekly limit
        ccburn monthly      # Explicit: Monthly credits (enterprise)
        ccburn --json       # JSON output
        ccburn --compact    # Single-line for status bars
        ccburn --once       # Print once and exit
    """
    if version:
        try:
            from importlib.metadata import version as get_version

            typer.echo(f"ccburn {get_version('ccburn')}")
        except Exception:
            typer.echo("ccburn 1.0.0")
        raise typer.Exit()

    # If no subcommand, auto-detect best available limit type
    if ctx.invoked_subcommand is None:
        console = Console()

        # Auto-detect which data is available
        limit_type = auto_detect_limit_type()

        if limit_type is None:
            console.print("[red]No usage data available.[/red]")
            console.print("\n[dim]Check that Claude Code is running and authenticated.[/dim]")
            raise typer.Exit(1)

        run_app(
            limit_type,
            json_output=json_output,
            once=once,
            compact=compact,
            since=since,
            interval=interval,
            debug=debug,
        )


if __name__ == "__main__":
    app()
