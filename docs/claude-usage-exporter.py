#!/usr/bin/env python3
"""
Claude Code Usage Limits Exporter for Prometheus

Reads Claude Code credentials and exports usage limits as Prometheus metrics.
Run with: python claude-usage-exporter.py

Metrics exposed on http://localhost:9100/metrics
"""

import json
import os
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error

# Configuration
CREDENTIALS_PATH = os.environ.get("CREDENTIALS_PATH", os.path.expanduser("~/.claude/.credentials.json"))
LISTEN_PORT = 9100
SCRAPE_INTERVAL = 60  # seconds between API calls

# Cache for metrics
metrics_cache = {
    "last_update": 0,
    "data": None,
    "error": None
}


def get_access_token():
    """Read access token from Claude credentials file."""
    try:
        with open(CREDENTIALS_PATH) as f:
            creds = json.load(f)
        return creds.get("claudeAiOauth", {}).get("accessToken")
    except Exception as e:
        return None


def fetch_usage_data():
    """Fetch usage data from Anthropic API."""
    access_token = get_access_token()
    if not access_token:
        raise Exception("No access token found in credentials")

    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "anthropic-beta": "oauth-2025-04-20"
        }
    )

    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read())


def get_cached_metrics():
    """Get metrics, using cache if recent enough."""
    now = time.time()
    if now - metrics_cache["last_update"] > SCRAPE_INTERVAL:
        try:
            metrics_cache["data"] = fetch_usage_data()
            metrics_cache["error"] = None
        except Exception as e:
            metrics_cache["error"] = str(e)
        metrics_cache["last_update"] = now
    return metrics_cache


def format_prometheus_metrics(cache):
    """Format metrics in Prometheus exposition format."""
    lines = []

    # Add metadata
    lines.append("# HELP claude_code_usage_utilization Current usage utilization percentage (0-100)")
    lines.append("# TYPE claude_code_usage_utilization gauge")
    lines.append("# HELP claude_code_usage_resets_at Unix timestamp when the limit resets")
    lines.append("# TYPE claude_code_usage_resets_at gauge")
    lines.append("# HELP claude_code_usage_scrape_success Whether the last scrape was successful")
    lines.append("# TYPE claude_code_usage_scrape_success gauge")

    if cache["error"]:
        lines.append(f'claude_code_usage_scrape_success 0')
        lines.append(f'# Error: {cache["error"]}')
        return "\n".join(lines)

    lines.append('claude_code_usage_scrape_success 1')

    data = cache["data"]
    if not data:
        return "\n".join(lines)

    # Map API fields to metric labels
    limit_types = {
        "five_hour": "5h_rolling",
        "seven_day": "7d_all_models",
        "seven_day_sonnet": "7d_sonnet",
        "seven_day_opus": "7d_opus",
        "seven_day_oauth_apps": "7d_oauth_apps"
    }

    for api_key, label in limit_types.items():
        limit_data = data.get(api_key)
        if limit_data and isinstance(limit_data, dict):
            utilization = limit_data.get("utilization")
            resets_at = limit_data.get("resets_at")

            if utilization is not None:
                lines.append(f'claude_code_usage_utilization{{limit="{label}"}} {utilization}')

            if resets_at:
                # Parse ISO timestamp to Unix timestamp
                try:
                    dt = datetime.fromisoformat(resets_at.replace("+00:00", "+00:00"))
                    unix_ts = dt.timestamp()
                    lines.append(f'claude_code_usage_resets_at{{limit="{label}"}} {unix_ts}')
                except:
                    pass

    # Extra usage (overage)
    extra = data.get("extra_usage", {})
    if extra and extra.get("is_enabled"):
        if extra.get("utilization") is not None:
            lines.append(f'claude_code_usage_utilization{{limit="extra_monthly"}} {extra["utilization"]}')

    return "\n".join(lines)


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for /metrics endpoint."""

    def do_GET(self):
        if self.path == "/metrics":
            cache = get_cached_metrics()
            metrics = format_prometheus_metrics(cache)

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(metrics.encode())
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress default logging
        pass


def main():
    print(f"Claude Code Usage Exporter starting on port {LISTEN_PORT}")
    print(f"Metrics available at http://localhost:{LISTEN_PORT}/metrics")
    print(f"Credentials path: {CREDENTIALS_PATH}")

    # Test credentials on startup
    try:
        data = fetch_usage_data()
        print(f"Initial fetch successful:")
        print(f"  5-hour: {data.get('five_hour', {}).get('utilization', 'N/A')}%")
        print(f"  7-day: {data.get('seven_day', {}).get('utilization', 'N/A')}%")
    except Exception as e:
        print(f"Warning: Initial fetch failed: {e}")

    server = HTTPServer(("0.0.0.0", LISTEN_PORT), MetricsHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
