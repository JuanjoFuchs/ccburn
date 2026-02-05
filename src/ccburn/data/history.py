"""SQLite history storage for usage snapshots."""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from .models import LimitData, LimitType, MonthlyLimitData, UsageSnapshot
except ImportError:
    from ccburn.data.models import LimitData, LimitType, MonthlyLimitData, UsageSnapshot


logger = logging.getLogger(__name__)


class HistoryDB:
    """SQLite database for storing usage snapshots."""

    SCHEMA = """
    -- Usage snapshots from API polling
    CREATE TABLE IF NOT EXISTS usage_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,  -- ISO 8601 UTC

        -- 5-hour rolling
        five_hour_utilization REAL,
        five_hour_resets_at TEXT,

        -- 7-day all models
        seven_day_all_utilization REAL,
        seven_day_all_resets_at TEXT,

        -- 7-day sonnet
        seven_day_sonnet_utilization REAL,
        seven_day_sonnet_resets_at TEXT,

        -- 7-day opus
        seven_day_opus_utilization REAL,
        seven_day_opus_resets_at TEXT,

        -- Monthly credits (enterprise)
        monthly_limit_cents INTEGER,
        monthly_used_credits_cents REAL,
        monthly_utilization REAL,
        monthly_resets_at TEXT,

        -- Raw API response for debugging
        raw_response TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON usage_snapshots(timestamp);

    -- Metadata
    CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """

    RETENTION_DAYS = 7

    def __init__(self, db_path: Path | str | None = None, in_memory: bool = False):
        """Initialize the history database.

        Args:
            db_path: Path to SQLite database file (default: ~/.ccburn/history.db)
            in_memory: If True, use in-memory database (for testing/fallback)
        """
        if in_memory:
            self.db_path = ":memory:"
        elif db_path is None:
            self.db_path = Path.home() / ".ccburn" / "history.db"
        else:
            self.db_path = Path(db_path)

        self._conn: sqlite3.Connection | None = None
        self._initialized = False

    def _ensure_dir(self) -> None:
        """Ensure the database directory exists."""
        if isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._ensure_dir()
            self._conn = sqlite3.connect(
                str(self.db_path) if isinstance(self.db_path, Path) else self.db_path,
                detect_types=sqlite3.PARSE_DECLTYPES,
                timeout=10.0,  # Wait up to 10 seconds for locks
                check_same_thread=False,  # Allow cross-thread access for loading spinner
            )
            self._conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent read/write performance
            self._conn.execute("PRAGMA journal_mode=WAL")

        if not self._initialized:
            self._initialize_schema()
            self._initialized = True

        return self._conn

    def _initialize_schema(self) -> None:
        """Initialize the database schema."""
        conn = self._conn
        if conn is None:
            return

        conn.executescript(self.SCHEMA)
        conn.commit()

        # Schema migration: Add monthly columns if they don't exist
        cursor = conn.execute("PRAGMA table_info(usage_snapshots)")
        columns = {row[1] for row in cursor.fetchall()}

        if "monthly_utilization" not in columns:
            conn.executescript("""
                ALTER TABLE usage_snapshots ADD COLUMN monthly_limit_cents INTEGER;
                ALTER TABLE usage_snapshots ADD COLUMN monthly_used_credits_cents REAL;
                ALTER TABLE usage_snapshots ADD COLUMN monthly_utilization REAL;
                ALTER TABLE usage_snapshots ADD COLUMN monthly_resets_at TEXT;
            """)
            conn.commit()

    def save_snapshot(self, snapshot: UsageSnapshot) -> None:
        """Save a usage snapshot to the database.

        Deduplicates by skipping if an identical snapshot exists within 5 seconds.

        Args:
            snapshot: The snapshot to save
        """
        conn = self._get_connection()

        # Extract data from snapshot
        five_hour_util = snapshot.session.utilization if snapshot.session else None

        # Check for recent duplicate (within 5 seconds with same utilization)
        recent_cutoff = (snapshot.timestamp - timedelta(seconds=5)).isoformat()
        cursor = conn.execute(
            """
            SELECT 1 FROM usage_snapshots
            WHERE timestamp > ?
              AND five_hour_utilization = ?
            LIMIT 1
            """,
            (recent_cutoff, five_hour_util),
        )
        if cursor.fetchone():
            # Skip duplicate
            return
        five_hour_resets = (
            snapshot.session.resets_at.isoformat() if snapshot.session else None
        )

        seven_day_util = snapshot.weekly.utilization if snapshot.weekly else None
        seven_day_resets = (
            snapshot.weekly.resets_at.isoformat() if snapshot.weekly else None
        )

        sonnet_util = (
            snapshot.weekly_sonnet.utilization if snapshot.weekly_sonnet else None
        )
        sonnet_resets = (
            snapshot.weekly_sonnet.resets_at.isoformat() if snapshot.weekly_sonnet else None
        )

        opus_util = snapshot.weekly_opus.utilization if snapshot.weekly_opus else None
        opus_resets = (
            snapshot.weekly_opus.resets_at.isoformat() if snapshot.weekly_opus else None
        )

        # Monthly credits data
        monthly_limit = (
            snapshot.monthly.monthly_limit_cents if snapshot.monthly else None
        )
        monthly_used = (
            snapshot.monthly.used_credits_cents if snapshot.monthly else None
        )
        monthly_util = snapshot.monthly.utilization if snapshot.monthly else None
        monthly_resets = (
            snapshot.monthly.resets_at.isoformat() if snapshot.monthly else None
        )

        conn.execute(
            """
            INSERT INTO usage_snapshots (
                timestamp,
                five_hour_utilization, five_hour_resets_at,
                seven_day_all_utilization, seven_day_all_resets_at,
                seven_day_sonnet_utilization, seven_day_sonnet_resets_at,
                seven_day_opus_utilization, seven_day_opus_resets_at,
                monthly_limit_cents, monthly_used_credits_cents,
                monthly_utilization, monthly_resets_at,
                raw_response
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.timestamp.isoformat(),
                five_hour_util,
                five_hour_resets,
                seven_day_util,
                seven_day_resets,
                sonnet_util,
                sonnet_resets,
                opus_util,
                opus_resets,
                monthly_limit,
                monthly_used,
                monthly_util,
                monthly_resets,
                snapshot.raw_response,
            ),
        )
        conn.commit()

    def get_latest_snapshot(self) -> UsageSnapshot | None:
        """Get the most recent snapshot from the database.

        Returns:
            Most recent UsageSnapshot, or None if no snapshots exist
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM usage_snapshots ORDER BY timestamp DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_snapshot(row)
        return None

    def get_latest_snapshot_age_seconds(self) -> float | None:
        """Get the age of the most recent snapshot in seconds.

        Returns:
            Age in seconds, or None if no snapshots exist
        """
        latest = self.get_latest_snapshot()
        if latest:
            now = datetime.now(timezone.utc)
            return (now - latest.timestamp).total_seconds()
        return None

    def get_snapshots(
        self,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[UsageSnapshot]:
        """Get historical snapshots.

        Args:
            since: Only return snapshots after this time
            limit: Maximum number of snapshots to return

        Returns:
            List of UsageSnapshot objects, sorted by timestamp ascending
        """
        conn = self._get_connection()

        query = "SELECT * FROM usage_snapshots"
        params: list = []

        if since:
            query += " WHERE timestamp >= ?"
            params.append(since.isoformat())

        query += " ORDER BY timestamp ASC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        snapshots = []
        for row in rows:
            snapshot = self._row_to_snapshot(row)
            if snapshot:
                snapshots.append(snapshot)

        return snapshots

    def get_snapshots_for_limit(
        self,
        limit_type: LimitType,
        since: datetime | None = None,
    ) -> list[UsageSnapshot]:
        """Get snapshots that have data for a specific limit type.

        Args:
            limit_type: Which limit to filter by
            since: Only return snapshots after this time

        Returns:
            List of snapshots with non-null data for the limit type
        """
        snapshots = self.get_snapshots(since=since)

        # Filter to only snapshots with data for this limit
        filtered = []
        for s in snapshots:
            if s.get_limit(limit_type) is not None:
                filtered.append(s)

        return filtered

    def _row_to_snapshot(self, row: sqlite3.Row) -> UsageSnapshot | None:
        """Convert a database row to a UsageSnapshot."""
        try:
            timestamp = datetime.fromisoformat(row["timestamp"])
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            # Parse session limit
            session = None
            if row["five_hour_utilization"] is not None:
                resets_at = datetime.fromisoformat(row["five_hour_resets_at"])
                if resets_at.tzinfo is None:
                    resets_at = resets_at.replace(tzinfo=timezone.utc)
                session = LimitData(
                    utilization=row["five_hour_utilization"],
                    resets_at=resets_at,
                    limit_type=LimitType.SESSION,
                )

            # Parse weekly limit
            weekly = None
            if row["seven_day_all_utilization"] is not None:
                resets_at = datetime.fromisoformat(row["seven_day_all_resets_at"])
                if resets_at.tzinfo is None:
                    resets_at = resets_at.replace(tzinfo=timezone.utc)
                weekly = LimitData(
                    utilization=row["seven_day_all_utilization"],
                    resets_at=resets_at,
                    limit_type=LimitType.WEEKLY,
                )

            # Parse sonnet limit
            weekly_sonnet = None
            if row["seven_day_sonnet_utilization"] is not None:
                resets_at = datetime.fromisoformat(row["seven_day_sonnet_resets_at"])
                if resets_at.tzinfo is None:
                    resets_at = resets_at.replace(tzinfo=timezone.utc)
                weekly_sonnet = LimitData(
                    utilization=row["seven_day_sonnet_utilization"],
                    resets_at=resets_at,
                    limit_type=LimitType.WEEKLY_SONNET,
                )

            # Parse opus limit
            weekly_opus = None
            if row["seven_day_opus_utilization"] is not None:
                resets_at = datetime.fromisoformat(row["seven_day_opus_resets_at"])
                if resets_at.tzinfo is None:
                    resets_at = resets_at.replace(tzinfo=timezone.utc)
                weekly_opus = LimitData(
                    utilization=row["seven_day_opus_utilization"],
                    resets_at=resets_at,
                    limit_type=LimitType.WEEKLY,  # Same window as weekly
                )

            # Parse monthly credits
            monthly = None
            monthly_util = row["monthly_utilization"] if "monthly_utilization" in row.keys() else None
            if monthly_util is not None:
                resets_at = datetime.fromisoformat(row["monthly_resets_at"])
                if resets_at.tzinfo is None:
                    resets_at = resets_at.replace(tzinfo=timezone.utc)
                monthly = MonthlyLimitData(
                    monthly_limit_cents=row["monthly_limit_cents"],
                    used_credits_cents=row["monthly_used_credits_cents"],
                    utilization=monthly_util,
                    resets_at=resets_at,
                )

            return UsageSnapshot(
                timestamp=timestamp,
                session=session,
                weekly=weekly,
                weekly_sonnet=weekly_sonnet,
                weekly_opus=weekly_opus,
                monthly=monthly,
                raw_response=row["raw_response"],
            )
        except (ValueError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse snapshot row: {e}")
            return None

    def prune_old_data(self) -> int:
        """Remove data older than retention period.

        Returns:
            Number of rows deleted
        """
        conn = self._get_connection()
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.RETENTION_DAYS)

        cursor = conn.execute(
            "DELETE FROM usage_snapshots WHERE timestamp < ?",
            (cutoff.isoformat(),),
        )
        conn.commit()

        deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"Pruned {deleted} old snapshots")

        return deleted

    def clear_history(self) -> int:
        """Clear all history data.

        Returns:
            Number of rows deleted
        """
        conn = self._get_connection()

        cursor = conn.execute("DELETE FROM usage_snapshots")
        conn.commit()

        deleted = cursor.rowcount
        logger.info(f"Cleared {deleted} snapshots from history")

        return deleted

    def get_snapshot_count(self) -> int:
        """Get the total number of snapshots in the database.

        Returns:
            Number of snapshots
        """
        conn = self._get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM usage_snapshots")
        return cursor.fetchone()[0]

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._initialized = False

    def __enter__(self) -> "HistoryDB":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
