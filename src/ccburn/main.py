"""ccburn - Terminal-based Claude Code usage limit visualizer."""

import sys

# Fast path: `ccburn collect` bypasses Typer entirely for minimal latency.
# This runs before any heavy imports (~80ms vs ~350ms).
if len(sys.argv) >= 2 and sys.argv[1] == "collect":
    try:
        from .collect import main as _collect_main
    except ImportError:
        from ccburn.collect import main as _collect_main

    _collect_main()
    sys.exit(0)

import typer

try:
    from .cli import (
        CompactOption,
        DebugOption,
        JsonOption,
        OnceOption,
        PollIntervalOption,
        SessionIntervalOption,
        SinceOption,
        UntilOption,
        register_commands,
        run_app,
    )
except ImportError:
    from ccburn.cli import (
        CompactOption,
        DebugOption,
        JsonOption,
        OnceOption,
        PollIntervalOption,
        SessionIntervalOption,
        SinceOption,
        UntilOption,
        register_commands,
        run_app,
    )


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
    until: str = UntilOption,
    interval: int = SessionIntervalOption,
    poll_interval: int = PollIntervalOption,
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
        run_app(
            None,  # Auto-detect from fetched data
            json_output=json_output,
            once=once,
            compact=compact,
            since=since,
            until=until,
            interval=interval,
            poll_interval=poll_interval,
            debug=debug,
        )


if __name__ == "__main__":
    app()
