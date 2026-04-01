# Statusline rate_limits Research

## Summary

Claude Code v2.1.80 added a `rate_limits` field to the statusline JSON input, enabling tools like ccburn to receive usage data directly from Claude Code without making API calls. However, this field is **not available for enterprise accounts**.

## Discovery (April 2026)

### How we found it

- GitHub issue [#30930](https://github.com/anthropics/claude-code/issues/30930) comment by @rethab pointed to the v2.1.80 changelog
- @skibidiskib's [claude-web-usage](https://github.com/skibidiskib/claude-web-usage) project documented the approach for macOS
- We implemented `ccburn collect` to pipe statusline JSON into the history DB

### The field

Added in Claude Code v2.1.80 (March 19, 2026). The statusline JSON now includes:

```json
{
  "rate_limits": {
    "five_hour": {
      "used_percentage": 42,
      "resets_at": 1774393200
    },
    "seven_day": {
      "used_percentage": 15,
      "resets_at": 1774436400
    }
  }
}
```

- `used_percentage`: 0-100 scale
- `resets_at`: Unix epoch timestamp (int), NOT ISO string

### Enterprise limitation

Tested on v2.1.89 (April 1, 2026):

| Account type | `rate_limits` in statusline | Data available |
|---|---|---|
| **Pro / Max** | Yes (`five_hour`, `seven_day`) | Session + weekly |
| **Enterprise** | **No** — field is absent | Only `extra_usage` via API (monthly credits) |

Enterprise accounts use monthly credit budgets (`extra_usage` block) instead of session/weekly windows. The `rate_limits` field is simply not populated for enterprise plans.

### Verified statusline JSON keys

**Enterprise** (no rate_limits):
```
session_id, transcript_path, cwd, session_name, model, workspace,
version, output_style, cost, context_window, exceeds_200k_tokens
```

**Pro/Max** (has rate_limits):
```
session_id, transcript_path, cwd, model, workspace, version,
output_style, cost, context_window, exceeds_200k_tokens, rate_limits
```

## Impact on ccburn

### Data source strategy by account type

**Pro/Max accounts:**
1. `ccburn collect` (statusline) -> DB (recommended, zero API calls)
2. OAuth API (may hit 429)
3. Claude Desktop cookies + curl (default profile only)
4. DB history fallback

**Enterprise accounts:**
1. OAuth API (may hit 429)
2. Claude Desktop cookies + curl (default profile only)
3. DB history fallback

`ccburn collect` still works for enterprise (passes through JSON, doesn't break the pipe) but doesn't write any data since there's no `rate_limits` in the input.

### Configuration recommendation

**Pro/Max:** Add `ccburn collect |` before your statusline command:
```json
"command": "ccburn collect | npx -y ccstatusline@latest"
```

**Enterprise:** No need for `ccburn collect` — use the statusline command directly:
```json
"command": "npx -y ccstatusline@latest"
```

## Technical details

### resets_at format

The statusline uses **Unix epoch integers** for `resets_at`, while the OAuth API uses **ISO 8601 strings**. `ccburn collect` handles both formats via `normalize_resets_at()` in `collect.py`.

### Performance

`ccburn collect` uses a fast path that bypasses Typer/Rich imports:
- Fast path: ~160ms (stdlib only: json, sqlite3, datetime)
- Typer path: ~500ms (imports Rich, Typer, plotext, etc.)

The fast path is triggered by checking `sys.argv[1] == "collect"` in `main.py` before any heavy imports.

### References

- [Claude Code v2.1.80 changelog](https://code.claude.com/docs/en/changelog)
- [statusline docs](https://code.claude.com/docs/en/statusline)
- [rethab's statusline script](https://github.com/rethab/dotfiles/blob/ad39e5884edafdb226d4198fac8c27aa07414403/.claude/statusline-command.sh)
- [Feature: Expose rate limit in statusLine JSON (#27915)](https://github.com/anthropics/claude-code/issues/27915)
