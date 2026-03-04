# Changelog

All notable changes to ccburn will be documented in this file.

## [0.5.0] - 2026-03-04

### Added

- **`--until` flag** for controlling the right edge of the display when using `--since`:
  - `--until now` (default): sliding window, both edges move with time
  - `--until end`: crop left edge but keep window end, making projections and depletion visible
  - `--until depleted`: zoom to projected depletion time with 5% padding, falls back to window end
  - Validation: `--until` requires `--since` to be set

### Fixed

- **Monthly utilization recalculation**: when the monthly credit limit changes (e.g., $300 to $600), historical snapshots are now recalculated against the current limit so burn rate regression and chart display remain accurate
- **Auto-detect 429 rate limit error**: eliminated a double API call that could trigger HTTP 429 when auto-detecting the limit type; detection now happens inside `CCBurnApp.run()` reusing the first fetch
- **Reset time format for monthly windows**: "Resets Sat 7:00 PM" is now "Resets Sat 2/28 7PM" when the reset is more than 7 days away, removing ambiguity

### Removed

- **Automatic snapshot pruning**: the 7-day retention policy was deleting historical data needed for monthly views; snapshots are now kept indefinitely (DB size is negligible)

### Changed

- Updated AGENTS.md with release procedure documentation
