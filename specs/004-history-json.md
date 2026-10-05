---
id: "004"
title: ccburn history --json, for tools that share ccburn's data
status: pending          # pending | in_progress | complete
blocked_by: []
blocks: []
---

# `ccburn history --json`

## Overview

ccburn keeps every reading in a SQLite history (`<data dir>/history.db`), fed by `ccburn collect` from the Claude Code status line of every session, or by ccburn's own fetches. Other tools can't read it without a SQLite driver. The first such tool is [ccburn-mod](https://github.com/JuanjoFuchs/ccburn-mod), a Claude Code mod that draws ccburn's chart inside Claude Code. Its runtime has no SQLite and no Node, but it can run a host command.

This spec adds one read-only command that prints the history as JSON, so a tool that can run `ccburn` sees exactly what ccburn sees. Writing goes the other way through the existing `ccburn collect` (stdin: the status line's `rate_limits` JSON), unchanged.

> **Completion rule:** This spec is not complete until all acceptance criteria are verified through pytest and a run against a real history database. Build-only verification is insufficient. The agent must iterate until verification passes.

## Goals

- Any tool that can run a command can read ccburn's history, for the same Claude Code profile ccburn uses.
- Fast enough to call once a minute.

## Requirements

### Functional Requirements

- **FR1.** `ccburn history --json` prints one JSON object to stdout and exits 0:
  ```json
  {
    "version": 1,
    "data_dir": "C:\\Users\\me\\.ccburn-work",
    "snapshots": [
      {
        "timestamp": "2026-10-05T21:27:15.349359+00:00",
        "limits": {
          "five_hour": { "used_percentage": 6.0, "resets_at": "2026-10-06T01:00:00+00:00" },
          "seven_day": { "used_percentage": 6.0, "resets_at": "2026-10-12T14:00:00+00:00" }
        }
      }
    ]
  }
  ```
  - Snapshots are oldest first.
  - `limits` holds `five_hour`, `seven_day`, `seven_day_sonnet` and `seven_day_opus`, each only when that snapshot has a value for it.
  - `used_percentage` is on the 0–100 scale, the scale the status line uses.
  - `resets_at` is the stored ISO string.
- **FR2.** `--since-hours N` (default 168) limits output to snapshots with `timestamp` at or after now − N hours.
- **FR3.** The data directory follows `CLAUDE_CONFIG_DIR` exactly as every other ccburn command does (`~/.claude` → `~/.ccburn`, `~/.claude-work` → `~/.ccburn-work`).
- **FR4.** No history database yet prints `"snapshots": []` and exits 0. The command never creates the database or its directory.
- **FR5.** Fast path, like `collect`: `ccburn history` skips the Typer/Rich imports.
- **FR6.** `ccburn describe` lists the command and its output contract.

### Non-Functional Requirements

- **NFR1.** Under 300 ms on a database of 10,000 snapshots (stdlib only: json, sqlite3, datetime).
- **NFR2.** Read-only: opens the database with SQLite's `mode=ro` URI so it never writes or locks out `collect`.

### Technical Constraints

- **TC1.** No change to the database schema or to `ccburn collect`.

## Implementation Tasks

- [ ] Standalone module for the command (stdlib only) and its fast path in `main.py`.
- [ ] A `history` command registered in the Typer app (so it shows in `--help`) that delegates to the module.
- [ ] `describe` entry.
- [ ] Tests.
- [ ] README and CHANGELOG lines.

## Acceptance Criteria

- [ ] AC1: Against a temp `CLAUDE_CONFIG_DIR` with three snapshots written by `collect`, `ccburn history --json` prints them oldest first with `used_percentage` equal to what `collect` received. — `integration`
- [ ] AC2: `--since-hours 1` drops a snapshot older than an hour. — `integration`
- [ ] AC3: With no database, the output is `{"version": 1, ..., "snapshots": []}`, exit 0, and no file or directory is created. — `integration`
- [ ] AC4: A snapshot with only `five_hour` set has no `seven_day` key. — `integration`
- [ ] AC5: `ccburn --help` lists `history`, and `ccburn describe` documents it. — `integration`
- [ ] AC6: Against the real work-profile database, the command prints the live readings in under 300 ms. — `manual` (a real database on this machine; timing depends on the host)

## Testing Approach

`pytest tests/test_history_export.py` runs the command as a module against temp profiles (`collect` writes, `history` reads); `ruff check`. Then one run against a real profile.

## Usage Examples

```bash
ccburn history --json
ccburn history --json --since-hours 5
CLAUDE_CONFIG_DIR=~/.claude-work ccburn history --json
```

## Out of Scope

- Monthly credits (`extra_usage`) in the output.
- Any write path other than the existing `collect`.
- Non-JSON output formats.

## References

- `src/ccburn/collect.py`: the stdin contract and the schema this reads.
- ccburn-mod spec 002 (the consumer).
