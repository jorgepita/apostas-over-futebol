"""
tests/test_backup_retention.py

Coverage for src/backup/backup_retention.py — index-based, per-type
retention (scheduled count cap, manual age cap, critical unlimited by
default / optional count cap), oldest-first eviction, and R2-object-then-
index-entry removal ordering. See docs/09_Architecture_Decisions.md
ADR-020.

Run with:  python -m pytest tests/test_backup_retention.py -v
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backup import backup_index
from src.backup.backup_retention import run_retention
from src.backup.r2_client import FakeR2Client

DEFAULT_CFG = {"scheduled_max_count": 60, "manual_max_age_days": 90, "critical_max_count": None}


def _iso(dt):
    return dt.isoformat()


def _seed(client, backup_id, backup_type, created_at):
    key = f"backups/{backup_type}/{backup_id}.zip"
    client.put_object(key, b"x" * 10)
    backup_index.add_entry(client, {
        "id": backup_id, "type": backup_type, "key": key, "createdAt": created_at,
    })


def test_scheduled_count_cap_evicts_oldest_first():
    client = FakeR2Client()
    now = datetime.now(timezone.utc)
    for i in range(5):
        _seed(client, f"s{i}", "scheduled", _iso(now - timedelta(hours=5 - i)))  # s0 oldest ... s4 newest

    result = run_retention(client, {**DEFAULT_CFG, "scheduled_max_count": 3})

    evicted_ids = {e["id"] for e in result["evicted"]}
    assert evicted_ids == {"s0", "s1"}  # 5 - 3 = 2 oldest evicted

    remaining = {b["id"] for b in backup_index.read_index(client)["backups"]}
    assert remaining == {"s2", "s3", "s4"}

    # The R2 objects themselves must be gone too, not just the index entries.
    assert client.list_objects("backups/scheduled/s0.zip") == []


def test_scheduled_under_cap_evicts_nothing():
    client = FakeR2Client()
    now = datetime.now(timezone.utc)
    _seed(client, "s0", "scheduled", _iso(now))
    result = run_retention(client, {**DEFAULT_CFG, "scheduled_max_count": 60})
    assert result["evicted"] == []


def test_manual_age_cap_evicts_only_entries_older_than_cutoff():
    client = FakeR2Client()
    now = datetime.now(timezone.utc)
    _seed(client, "old_manual", "manual", _iso(now - timedelta(days=100)))
    _seed(client, "recent_manual", "manual", _iso(now - timedelta(days=10)))

    result = run_retention(client, {**DEFAULT_CFG, "manual_max_age_days": 90})

    evicted_ids = {e["id"] for e in result["evicted"]}
    assert evicted_ids == {"old_manual"}
    remaining = {b["id"] for b in backup_index.read_index(client)["backups"]}
    assert remaining == {"recent_manual"}


def test_critical_unlimited_by_default_evicts_nothing_regardless_of_age_or_count():
    client = FakeR2Client()
    now = datetime.now(timezone.utc)
    for i in range(10):
        _seed(client, f"c{i}", "critical", _iso(now - timedelta(days=400 + i)))

    result = run_retention(client, DEFAULT_CFG)  # critical_max_count: None
    assert result["evicted"] == []
    assert len(backup_index.read_index(client)["backups"]) == 10


def test_critical_respects_explicit_count_cap_when_configured():
    client = FakeR2Client()
    now = datetime.now(timezone.utc)
    for i in range(5):
        _seed(client, f"c{i}", "critical", _iso(now - timedelta(hours=5 - i)))

    result = run_retention(client, {**DEFAULT_CFG, "critical_max_count": 2})
    evicted_ids = {e["id"] for e in result["evicted"]}
    assert evicted_ids == {"c0", "c1", "c2"}
    remaining = {b["id"] for b in backup_index.read_index(client)["backups"]}
    assert remaining == {"c3", "c4"}


def test_retention_types_are_independent_of_each_other():
    client = FakeR2Client()
    now = datetime.now(timezone.utc)
    for i in range(3):
        _seed(client, f"s{i}", "scheduled", _iso(now - timedelta(hours=3 - i)))
    _seed(client, "m0", "manual", _iso(now - timedelta(days=1)))
    _seed(client, "c0", "critical", _iso(now - timedelta(days=500)))

    result = run_retention(client, {**DEFAULT_CFG, "scheduled_max_count": 1})
    evicted_ids = {e["id"] for e in result["evicted"]}
    assert evicted_ids == {"s0", "s1"}  # only scheduled entries touched
    remaining = {b["id"] for b in backup_index.read_index(client)["backups"]}
    assert remaining == {"s2", "m0", "c0"}


def test_failed_r2_delete_keeps_index_entry_and_is_reported_as_failed():
    class _StuckDeleteClient(FakeR2Client):
        def delete_object(self, key):
            if "stuck" in key:
                raise RuntimeError("simulated R2 delete failure")
            super().delete_object(key)

    client = _StuckDeleteClient()
    now = datetime.now(timezone.utc)
    _seed(client, "stuck_old", "scheduled", _iso(now - timedelta(hours=2)))
    _seed(client, "ok_newer", "scheduled", _iso(now - timedelta(hours=1)))

    result = run_retention(client, {**DEFAULT_CFG, "scheduled_max_count": 1})

    assert any(f["id"] == "stuck_old" for f in result["failed"])
    # The index entry for the failed eviction must still exist — dropping
    # it would orphan the R2 object with nothing left pointing at it.
    remaining_ids = {b["id"] for b in backup_index.read_index(client)["backups"]}
    assert "stuck_old" in remaining_ids


def test_evicting_an_already_missing_object_still_removes_the_index_entry():
    client = FakeR2Client()
    now = datetime.now(timezone.utc)
    _seed(client, "s0", "scheduled", _iso(now - timedelta(hours=2)))
    _seed(client, "s1", "scheduled", _iso(now - timedelta(hours=1)))
    client._external_delete("backups/scheduled/s0.zip")  # drift: gone from R2, still in index

    result = run_retention(client, {**DEFAULT_CFG, "scheduled_max_count": 1})
    assert any(e["id"] == "s0" for e in result["evicted"])
    remaining_ids = {b["id"] for b in backup_index.read_index(client)["backups"]}
    assert remaining_ids == {"s1"}
