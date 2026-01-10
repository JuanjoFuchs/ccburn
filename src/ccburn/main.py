"""ccburn - Terminal-based Claude Code usage limit visualizer."""


import typer

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
    Shows 5-hour rolling session limit by default.

    \b
    Examples:
        ccburn              # Live TUI showing session limit
        ccburn session      # Same as above (explicit)
        ccburn weekly       # Show 7-day weekly limit
        ccburn weekly-sonnet # Show 7-day Sonnet limit
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

    # If no subcommand, default to session
    if ctx.invoked_subcommand is None:
        run_app(
            LimitType.SESSION,
            json_output=json_output,
            once=once,
            compact=compact,
            since=since,
            interval=interval,
            debug=debug,
        )


if __name__ == "__main__":
    app()
