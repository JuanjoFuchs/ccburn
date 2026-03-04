# Claude Code Agent Instructions

## Project Overview

**ccburn** is a terminal-based CLI tool for visualizing Claude Code usage limits. It displays real-time burn-up charts showing session and weekly usage against budget pace.

## Quick Start

```bash
# venv is already activated - just run directly
ccburn              # Session limit TUI
ccburn weekly       # Weekly limit TUI
ccburn --compact    # Single-line output for status bars
ccburn --json       # JSON output for automation
pytest              # Run tests
ruff check src/ tests/  # Lint
```

## Architecture

```
src/ccburn/
├── main.py          # Typer CLI entry point
├── cli.py           # CLI commands and options
├── app.py           # Main application class (CCBurnApp)
├── data/
│   ├── models.py    # Data models (LimitType, LimitData, UsageSnapshot)
│   ├── credentials.py # Reads Claude Code credentials from ~/.claude/
│   ├── usage_client.py # HTTP client for Anthropic usage API
│   └── history.py   # SQLite persistence for usage snapshots
├── display/
│   ├── layout.py    # Rich layout composition (BurnupLayout)
│   ├── chart.py     # Plotext burn-up chart rendering
│   └── gauges.py    # Header, progress bars, compact output
└── utils/
    ├── calculator.py  # Burn rate, budget pace, projections
    └── formatting.py  # Time formatting, colors
```

## Key Concepts

### Limit Types
- `LimitType.SESSION` - 5-hour rolling window
- `LimitType.WEEKLY` - 7-day rolling window
- `LimitType.WEEKLY_SONNET` - 7-day Sonnet-specific limit

### Budget Pace
The expected utilization based on elapsed time in the window. If 2.5 hours have passed in a 5-hour session window, budget pace is 50%.

### Pace Indicators
- 🧊 Behind pace (ratio < 0.85) - under budget
- 🔥 On pace (0.85-1.15) - tracking budget
- 🚨 Ahead of pace (ratio > 1.15) - over budget

### Output Modes
1. **TUI** (default) - Full-screen Rich Live display with chart
2. **Compact** (`--compact`) - Single line for tmux/status bars
3. **JSON** (`--json`) - Machine-readable output
4. **Once** (`--once`) - Single render, no live updates

## Testing

```bash
pytest                    # All tests
pytest -v                 # Verbose
pytest tests/test_calculator.py  # Single file
pytest -k "test_budget"   # Pattern match
```

Tests use fixtures from `tests/conftest.py` for mock data.

## Code Style

- **Formatter/Linter**: ruff
- **Line length**: 100
- **Python**: 3.10+ (uses `|` union types, match statements)

```bash
ruff check src/ tests/    # Check
ruff check --fix src/     # Auto-fix
```

## Commit Convention

Uses **gitmoji** for commit messages.


### Common Emojis

- 🎉 `:tada:` - Initial commit
- ✨ `:sparkles:` - New feature
- 🐛 `:bug:` - Bug fix
- 📝 `:memo:` - Documentation
- ♻️ `:recycle:` - Refactor
- 📦 `:package:` - Packaging/dependencies
- 🔖 `:bookmark:` - Version bump

## Release Procedure

### Version Numbering

Follow semantic versioning (MAJOR.MINOR.PATCH):
- **PATCH** (0.2.x): Bug fixes only
- **MINOR** (0.x.0): New features (backwards compatible)
- **MAJOR** (x.0.0): Breaking changes

### Release Steps

1. **Update versions** in both files:
   - `pyproject.toml` - Python package version
   - `npm/package.json` - npm package version

2. **Stage and commit** version bump:
   ```bash
   git add pyproject.toml npm/package.json
   # Use gitmoji with :bookmark: emoji
   ```

3. **Tag and push**:
   ```bash
   git tag v0.x.x
   git push && git push --tags
   ```

4. **CI/CD** (automated on tag push):
   - GitHub Actions builds releases
   - PyPI publish triggered
   - WinGet manifest updated

## Specs

Specifications live in `specs/`:


## Key Files to Know

| File | Purpose |
|------|---------|
| `app.py` | Main loop, data fetching, state management |
| `chart.py` | Plotext chart rendering, X/Y axis, "Now" line |
| `gauges.py` | `get_pace_emoji()`, `create_header()`, `create_compact_output()` |
| `calculator.py` | `calculate_budget_pace()`, `calculate_burn_metrics()` |
| `history.py` | SQLite operations, `get_snapshots_for_limit()` |

## Common Tasks

### Add a new CLI option
1. Add option in `cli.py` (use Typer annotations)
2. Pass through `main.py` commands to `CCBurnApp`
3. Handle in `app.py`

### Modify chart appearance
Edit `display/chart.py` - the `BurnupChart` class handles all plotext rendering.

### Change pace thresholds
Edit `get_pace_emoji()` in `display/gauges.py` (currently 0.85/1.15).

### Add new output format
1. Add flag in `cli.py`
2. Add `_run_<format>()` method in `app.py`
3. Call from `app.py:run()`

## Environment

- Python venv is pre-activated
- Package installed in editable mode (`pip install -e .`)
- SQLite DB stored in `~/.local/share/ccburn/history.db`
- Credentials read from `~/.claude/` (Claude Code config)

## Debugging

```bash
ccburn --debug          # Shows raw API response
ccburn --once --debug   # Single fetch with debug output
```

## Dependencies

- **typer** - CLI framework
- **rich** - Terminal formatting, Live display
- **plotext** - Terminal charts
- **httpx** - HTTP client for API calls

Dev dependencies: pytest, ruff, mypy, build, twine, pyinstaller
