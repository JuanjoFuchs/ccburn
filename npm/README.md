# ccburn

Terminal-based Claude Code usage limit visualizer with real-time burn-up charts.

## Installation

```bash
# Run directly with npx
npx ccburn

# Or install globally
npm install -g ccburn
```

## Usage

```bash
ccburn              # Session limit TUI
ccburn weekly       # Weekly limit
ccburn --compact    # Single line for status bars
ccburn --json       # JSON output for automation
```

## Features

- **Real-time burn-up charts** with budget pace line
- **Pace indicators**: 🧊 behind pace, 🔥 on pace, 🚨 burning too hot
- **Session, Weekly, and Weekly-Sonnet limits**
- **Compact mode** for tmux/status bars
- **JSON output** for scripting

## Requirements

- Claude Code installed with valid credentials

## Alternative Installation

If npm installation fails, you can install via pip:

```bash
pip install ccburn
```

## Links

- [GitHub](https://github.com/JuanjoFuchs/ccburn)
- [PyPI](https://pypi.org/project/ccburn/)

## License

MIT
