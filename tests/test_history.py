"""Tests for history database."""

from datetime import datetime, timedelta, timezone

import pytest

from ccburn.data.history import HistoryDB
from ccburn.data.models import LimitType, LimitData, UsageSnapshot


class TestHistoryDB:
    """Tests for HistoryDB."""

    def test_create_in_memory(self):
        """Should create in-memory database."""
        with HistoryDB(in_memory=True) as db:
            assert db.get_snapshot_count() == 0

    def test_save_and_retrieve_snapshot(self, sample_snapshot):
        """Should save and retrieve snapshots."""
        with HistoryDB(in_memory=True) as db:
            db.save_snapshot(sample_snapshot)

            snapshots = db.get_snapshots()
            assert len(snapshots) == 1
            assert snapshots[0].session is not None
            assert snapshots[0].session.utilization == pytest.approx(0.62, abs=0.01)

    def test_get_snapshots_since(self, sample_snapshot):
        """Should filter snapshots by time."""
        with HistoryDB(in_memory=True) as db:
            db.save_snapshot(sample_snapshot)

            # Should find snapshot
            since_before = sample_snapshot.timestamp - timedelta(hours=1)
            snapshots = db.get_snapshots(since=since_before)
            assert len(snapshots) == 1

            # Should not find snapshot
            since_after = sample_snapshot.timestamp + timedelta(hours=1)
            snapshots = db.get_snapshots(since=since_after)
            assert len(snapshots) == 0

    def test_get_snapshots_for_limit(self, sample_snapshot):
        """Should filter snapshots by limit type."""
        with HistoryDB(in_memory=True) as db:
            db.save_snapshot(sample_snapshot)

            # Should find for session
            snapshots = db.get_snapshots_for_limit(LimitType.SESSION)
            assert len(snapshots) == 1

            # Create snapshot without session data
            no_session = UsageSnapshot(
                timestamp=datetime.now(timezone.utc),
                session=None,
                weekly=sample_snapshot.weekly,
                weekly_sonnet=None,
                weekly_opus=None,
            )
            db.save_snapshot(no_session)

            # Should still only find 1 for session
            snapshots = db.get_snapshots_for_limit(LimitType.SESSION)
            assert len(snapshots) == 1

    def test_clear_history(self, sample_snapshot):
        """Should clear all snapshots."""
        with HistoryDB(in_memory=True) as db:
            db.save_snapshot(sample_snapshot)
            assert db.get_snapshot_count() == 1

            deleted = db.clear_history()
            assert deleted == 1
            assert db.get_snapshot_count() == 0

    def test_prune_old_data(self):
        """Should prune data older than retention period."""
        with HistoryDB(in_memory=True) as db:
            # Create old snapshot
            old_time = datetime.now(timezone.utc) - timedelta(days=10)
            old_snapshot = UsageSnapshot(
                timestamp=old_time,
                session=LimitData(
                    utilization=0.5,
                    resets_at=old_time + timedelta(hours=5),
                    limit_type=LimitType.SESSION,
                ),
                weekly=None,
                weekly_sonnet=None,
                weekly_opus=None,
            )
            db.save_snapshot(old_snapshot)

            # Create recent snapshot
            recent_time = datetime.now(timezone.utc)
            recent_snapshot = UsageSnapshot(
                timestamp=recent_time,
                session=LimitData(
                    utilization=0.6,
                    resets_at=recent_time + timedelta(hours=5),
                    limit_type=LimitType.SESSION,
                ),
                weekly=None,
                weekly_sonnet=None,
                weekly_opus=None,
            )
            db.save_snapshot(recent_snapshot)

            assert db.get_snapshot_count() == 2

            # Prune old data
            deleted = db.prune_old_data()
            assert deleted == 1
            assert db.get_snapshot_count() == 1

    def test_file_based_database(self, temp_db):
        """Should create file-based database."""
        with HistoryDB(db_path=temp_db) as db:
            snapshot = UsageSnapshot(
                timestamp=datetime.now(timezone.utc),
                session=LimitData(
                    utilization=0.5,
                    resets_at=datetime.now(timezone.utc) + timedelta(hours=5),
                    limit_type=LimitType.SESSION,
                ),
                weekly=None,
                weekly_sonnet=None,
                weekly_opus=None,
            )
            db.save_snapshot(snapshot)
            assert db.get_snapshot_count() == 1

        # Verify file was created
        assert temp_db.exists()

        # Verify data persists
        with HistoryDB(db_path=temp_db) as db:
            assert db.get_snapshot_count() == 1
