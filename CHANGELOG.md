# Changelog

All notable changes to ccburn will be documented in this file.

## [0.7.0] - 2026-03-24

### Added

- **`ccburn collect` command**: pipe-safe statusline wrapper that extracts `rate_limits` from Claude Code's statusline JSON (v2.1.80+) and saves snapshots to the history DB. Passes stdin through unchanged so existing statusline commands continue to work. This is now the recommended data source — zero API calls, no rate limits, works for all profiles.
  ```json
  { "statusLine": { "command": "ccburn collect | your-statusline-command" } }
  ```
- **`ccburn describe` command**: outputs structured JSON for AI agents with setup instructions, data source strategy chain, all commands/flags, and resolved paths. Enables agents to auto-configure ccburn.
- **Multi-profile support**: respects `CLAUDE_CONFIG_DIR` env var so each Claude Code profile gets isolated credentials, history DB, and log files (`~/.claude-personal` → `~/.ccburn-personal`).
- **Persistent debug logging**: all API calls, strategy decisions, and errors logged to `~/.ccburn/ccburn.log` (rotating, 1MB max). `--debug` flag now shows which strategy succeeded (oauth, web cookies+curl, statusline cache).

### Fixed

- **Cookie retry on failure**: removed permanent `_cookies_failed` flag that prevented cookie re-extraction for the entire session. Cookies are now re-extracted on every failure.
- **Cross-account data contamination**: cookie-based web API is now skipped for non-default profiles (`CLAUDE_CONFIG_DIR` set), preventing enterprise data from leaking into personal profile databases.
- **DB cache window**: increased from `interval/2` to 2 minutes so statusline-fed data survives between polling cycles without triggering unnecessary API calls.

## [0.6.0] - 2026-03-09

### Added

- **Web API fallback for OAuth 429**: when the OAuth usage endpoint returns persistent 429 errors, ccburn now decrypts Claude Desktop's Chromium cookies and calls the `claude.ai` web API via `curl`, which uses a separate rate limit bucket unaffected by the OAuth rate limiting. Strategy chain: OAuth API → Web API (cookies + curl) → DB cache.
  - **Windows**: DPAPI key decryption + AES-256-GCM cookie decryption. Briefly kills the Chromium network service subprocess to copy the locked Cookies DB (auto-respawns in ~10ms).
  - **macOS**: Keychain password + PBKDF2 key derivation + AES-128-CBC decryption. Reads past advisory file locks via `sqlite3` CLI.
- **`--since start` modifier**: use `--since start --until depleted` to show the full window through projected depletion.

### Fixed

- **`--until depleted` with `--since start`**: the depleted display window logic was incorrectly gated on `since_duration` being set; it now works independently.

### Removed

- **Token refresh on 429**: removed the OAuth token refresh workaround added in development — it races with Claude Code for one-time-use refresh tokens and is fundamentally incompatible with concurrent usage ([#24317](https://github.com/anthropics/claude-code/issues/24317)).

## [0.5.1] - 2026-03-05

### Fixed

- **Graceful fallback on API 429 rate limit**: when the `/api/oauth/usage` endpoint returns persistent 429 errors, ccburn now falls back to the most recent snapshot from the SQLite history DB instead of exiting with an error. A yellow staleness banner indicates when cached data is being used. Workaround for upstream issue ([#30930](https://github.com/anthropics/claude-code/issues/30930), [#31055](https://github.com/anthropics/claude-code/issues/31055), [#31021](https://github.com/anthropics/claude-code/issues/31021)).
- **429 retry with backoff**: HTTP 429 responses are now retried with exponential backoff (previously only 5xx errors were retried).

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
