# ccburn - Claude Code Burn Rate Monitor

A terminal-based tool for visualizing Claude Code usage limits with real-time burn-up charts.

## Background & Motivation

### The Problem

Claude Code users have no easy way to visualize their usage limit consumption over time. The existing options are:

1. **`/usage` command** - Shows current state, no history, no visualization
2. **ccusage** - Excellent for cost/token tables, but no charts and doesn't show actual limit utilization
3. **Grafana dashboards** - Requires running a full observability stack

### Key Finding: OTEL Metrics Don't Predict Limits

We built a correlation analysis between OTEL metrics and usage limit burn rate. **All correlations were weak (|r| < 0.3)**.

Why? OTEL metrics are missing **thinking tokens** - the invisible reasoning tokens that can be 3-10x the visible output and count fully against usage limits.

| What OTEL Tracks | What Counts Toward Limits |
|------------------|---------------------------|
| input, output, cacheRead, cacheCreation | All of those PLUS thinking tokens |

Other factors not in OTEL:
- **Model weighting**: Opus consumes ~5x more allocation than Sonnet
- **Cross-product usage**: claude.ai, Claude Code, and Desktop share limits
- **Thinking budget keywords**: "think hard", "ultrathink" increase consumption

### Implication

The **Usage API** is the only source of truth for limit consumption. ccburn will focus on visualizing Usage API data, not trying to derive limits from OTEL metrics.

---

## Product Vision

```
┌─────────────────────────────────────────────────────────────────┐
│ ccburn                                              ⏱ 2h 14m    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  5-Hour Rolling                    ████████████░░░░░░░░  62%    │
│                                                                 │
│  100%│                                                          │
│      │                                            ●━━━━         │
│   75%│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─●━━━╱─ ─ ─        │
│      │                                    ●━━━╱                 │
│   50%│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─●━━━╱─ ─ ─ ─ ─ ─ ─        │
│      │                            ●━━╱                          │
│   25%│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ●━━━━╱─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─        │
│      │              ●━━━━━━╱                                    │
│    0%│━━━━━━━━━━━━━╱                                            │
│      └──────────────────────────────────────────────────────    │
│       -5h        -4h        -3h        -2h        -1h      now  │
│                                                                 │
│  Weekly Limits                                                  │
│  All Models  ████████░░░░░░░░░░░░  42%    Resets in 4d 12h     │
│  Sonnet      ██████░░░░░░░░░░░░░░  38%    Resets in 4d 12h     │
│                                                                 │
│  Burn Rate: 12%/hr (moderate)     Est. empty: 3h 10m            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Two Modes

```bash
# Human mode - TUI with live updating charts
ccburn

# Claude mode - JSON snapshot for programmatic use
ccburn --json
```

The JSON mode allows Claude Code to invoke it via Bash and become "budget aware".

---

## Design Decisions

### 1. Standalone, Zero Dependencies on Observability Stack

ccburn should work without Docker, Prometheus, Grafana, or any external services. It only needs:
- Claude credentials at `~/.claude/.credentials.json`
- A place to store history: `~/.ccburn/history.db`

### 2. Self-Contained History via SQLite

The Usage API only returns current state. To show charts over time, ccburn will:
1. Poll the Usage API every 30-60 seconds
2. Store each data point in a local SQLite database
3. Query the database to render charts

This means charts build up over time as you use ccburn.

### 3. Complement ccusage, Don't Replace It

| Tool | Purpose |
|------|---------|
| **ccusage** | "What did I spend?" - tokens, costs, by model, from JSONL |
| **ccburn** | "How close am I to the limit?" - burn rate, time left, charts |

Different data sources, different questions answered.

### 4. Language: Python

Reasons:
- Rich ecosystem for TUI (Rich, Textual, plotext)
- Easy to install via pip/pipx
- Matches the existing claudefana tooling
- Simpler than TypeScript for a focused CLI tool

### 5. Library Stack

| Component | Library | Reason |
|-----------|---------|--------|
| TUI framework | **Rich** | Lightweight, beautiful output, no full TUI needed |
| Charts | **plotext** | Terminal plotting, works with Rich |
| Database | **sqlite3** | Built into Python, zero deps |
| HTTP | **urllib** | Built into Python, zero deps |
| CLI | **argparse** | Built into Python, zero deps |

Goal: Minimal external dependencies. Only Rich and plotext as non-stdlib deps.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          ccburn                                  │
├─────────────────────────────────────────────────────────────────┤
│  CLI Layer (cli.py)                                             │
│  ├── ccburn              (TUI mode - live updating)             │
│  ├── ccburn --json       (JSON output for Claude)               │
│  ├── ccburn --once       (Print once and exit)                  │
│  └── ccburn --compact    (Single-line status)                   │
├─────────────────────────────────────────────────────────────────┤
│  Core Library                                                    │
│  ├── usage_client.py    (Anthropic Usage API client)            │
│  ├── history.py         (SQLite storage for historical data)    │
│  ├── calculator.py      (Burn rate, predictions, estimates)     │
│  └── renderer.py        (Rich + plotext output)                 │
├─────────────────────────────────────────────────────────────────┤
│  Storage                                                         │
│  └── ~/.ccburn/history.db                                       │
├─────────────────────────────────────────────────────────────────┤
│  External                                                        │
│  └── ~/.claude/.credentials.json (OAuth tokens)                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## CLI Interface

### Commands

```bash
# Live TUI mode (default) - updates every 30s
ccburn

# JSON output for programmatic use
ccburn --json

# Print once and exit (for scripts)
ccburn --once

# Compact single-line output (for status bars)
ccburn --compact

# Specify refresh interval
ccburn --interval 60

# Show history for specific time range
ccburn --since 2h
ccburn --since 24h

# Clear stored history
ccburn --clear-history

# Debug: show raw API response
ccburn --debug
```

### JSON Output Format

```json
{
  "timestamp": "2026-01-08T14:32:00Z",
  "five_hour": {
    "utilization": 0.62,
    "resets_at": "2026-01-08T16:46:00Z",
    "minutes_remaining": 134
  },
  "seven_day": {
    "all_models": {
      "utilization": 0.42,
      "resets_at": "2026-01-12T00:00:00Z"
    },
    "sonnet": {
      "utilization": 0.38,
      "resets_at": "2026-01-12T00:00:00Z"
    }
  },
  "burn_rate": {
    "percent_per_hour": 0.12,
    "trend": "moderate",
    "estimated_empty_minutes": 190
  },
  "recommendation": "moderate_pace"
}
```

### Recommendations Logic

| Utilization | Burn Rate | Recommendation |
|-------------|-----------|----------------|
| < 50% | Any | `plenty_available` |
| 50-75% | Low | `on_track` |
| 50-75% | High | `moderate_pace` |
| 75-90% | Any | `conserve` |
| > 90% | Any | `critical` |

---

## Data Model

### SQLite Schema

```sql
CREATE TABLE usage_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,  -- ISO 8601

    -- 5-hour rolling
    five_hour_utilization REAL,
    five_hour_resets_at TEXT,

    -- 7-day all models
    seven_day_all_utilization REAL,
    seven_day_all_resets_at TEXT,

    -- 7-day sonnet
    seven_day_sonnet_utilization REAL,
    seven_day_sonnet_resets_at TEXT,

    -- Raw API response for debugging
    raw_response TEXT
);

CREATE INDEX idx_timestamp ON usage_snapshots(timestamp);
```

### Retention Policy

- Keep last 7 days of data
- Auto-prune on startup
- ~10KB per day at 30s intervals

---

## Usage API Integration

### Endpoint

```
GET https://api.anthropic.com/api/oauth/usage
Authorization: Bearer {accessToken}
anthropic-beta: oauth-2025-04-20
```

### Response Structure

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
  }
}
```

### Error Handling

| Scenario | Behavior |
|----------|----------|
| No credentials file | Exit with helpful error message |
| Token expired | Prompt user to restart Claude Code |
| API returns null | Show warning, continue with stale data |
| Network error | Show warning, retry with backoff |

---

## Visual Design

### Color Scheme

| Utilization | Color | Meaning |
|-------------|-------|---------|
| 0-50% | Green | Plenty available |
| 50-75% | Yellow | Monitor usage |
| 75-90% | Orange | Slow down |
| 90-100% | Red | Critical |

### Chart Style

- ASCII line chart using plotext
- X-axis: time (last 5 hours for 5h chart)
- Y-axis: utilization percentage (0-100%)
- Current value highlighted with marker
- Threshold lines at 75% and 90%

### Compact Mode

For embedding in status bars or tmux:

```
ccburn: 62% (2h14m) | 7d: 42%
```

Or with color:
```
🟡 62% ⏱2h14m
```

---

## Future Considerations

### Potential Features (Not MVP)

1. **MCP Server** - Let Claude query usage directly without Bash
2. **Notifications** - Desktop alerts at 80%, 95%
3. **tmux integration** - Status bar plugin
4. **Multi-account** - Support for team accounts
5. **Predictions** - ML-based "time to empty" estimates

### Integration with ccusage

Could potentially:
- Share history data format
- Provide a unified `cc` command
- Import ccusage cost data for correlation views

---

## Installation Plan

### PyPI Package

```bash
pip install ccburn
# or
pipx install ccburn
```

### Package Structure

```
ccburn/
├── pyproject.toml
├── README.md
├── LICENSE (MIT)
├── src/
│   └── ccburn/
│       ├── __init__.py
│       ├── __main__.py      # Entry point
│       ├── cli.py           # Argument parsing
│       ├── usage_client.py  # API client
│       ├── history.py       # SQLite storage
│       ├── calculator.py    # Burn rate math
│       └── renderer.py      # Rich + plotext output
└── tests/
    └── ...
```

### Entry Point

```toml
[project.scripts]
ccburn = "ccburn:main"
```

---

## References

- [ccusage](https://github.com/ryoppippi/ccusage) - Inspiration for naming and scope
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [plotext](https://github.com/piccolomo/plotext) - Terminal plotting
- [Claude Usage API](https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan)
- [Extended Thinking Docs](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)

### Related GitHub Issues

Feature requests we filed to improve Claude Code's telemetry:
- [#16942](https://github.com/anthropics/claude-code/issues/16942) - Export usage limit utilization via OTEL metrics
- [#16943](https://github.com/anthropics/claude-code/issues/16943) - Add thinking tokens to OTEL token_usage metric

Community issues requesting similar functionality:
- [#15366](https://github.com/anthropics/claude-code/issues/15366) - Usage limits in statusLine hook (11 reactions)
- [#12520](https://github.com/anthropics/claude-code/issues/12520) - Expose /usage data in statusLine
- [#10388](https://github.com/anthropics/claude-code/issues/10388) - Agent Token Usage API (7 reactions)
- [#777](https://github.com/anthropics/claude-code/issues/777) - Make agent aware of token usage (7 reactions)

---

## Open Questions

1. **Token refresh**: Should ccburn attempt to refresh expired OAuth tokens, or just prompt user?
2. **History sharing**: Worth making history DB compatible with other tools?
3. **Windows support**: Any special considerations for Windows paths/terminals?

---

*Spec created: January 8, 2026*
