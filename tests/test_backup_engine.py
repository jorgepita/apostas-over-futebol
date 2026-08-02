"""
tests/test_backup_engine.py

Coverage for src/backup/backup_engine.py::create_backup() — the core
create -> upload -> verify -> index -> retention cycle. Uses FakeR2Client
throughout (no real network I/O). See docs/09_Architecture_Decisions.md
ADR-020.

Run with:  python -m pytest tests/test_backup_engine.py -v
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backup import backup_index
from src.backup.backup_engine import BackupError, create_backup
from src.backup.r2_client import FakeR2Client

SAMPLE_FILES = {"cloud_state.json": b'{"a": 1}', "picks_history.csv": b"Data;Liga\n"}


def test_create_backup_uploads_verifies_and_indexes():
    client = FakeR2Client()
    result = create_backup("manual", files=SAMPLE_FILES, r2_client=client, reason="test")

    assert result["type"] == "manual"
    assert result["fileCount"] == 2
    assert result["key"].startswith("backups/manual/")
    assert result["key"].endswith(".zip")

    # The object genuinely exists in R2 (not just claimed by the result dict).
    stored = client.get_object(result["key"])
    assert len(stored) == result["sizeBytes"]

    index = backup_index.read_index(client)
    assert any(b["id"] == result["id"] for b in index["backups"])


def test_create_backup_rejects_invalid_type():
    client = FakeR2Client()
    with pytest.raises(BackupError):
        create_backup("nonsense", files=SAMPLE_FILES, r2_client=client)


def test_create_backup_rejects_empty_files():
    client = FakeR2Client()
    with pytest.raises(BackupError):
        create_backup("manual", files={}, r2_client=client)


def test_create_backup_raises_and_creates_no_index_entry_on_upload_failure():
    client = FakeR2Client()
    client.fail_next_put = True
    with pytest.raises(BackupError):
        create_backup("manual", files=SAMPLE_FILES, r2_client=client)

    index = backup_index.read_index(client)
    assert index["backups"] == []


def test_create_backup_cleans_up_and_raises_on_verify_failure():
    client = FakeR2Client()
    client.fail_next_head = True
    with pytest.raises(BackupError):
        create_backup("manual", files=SAMPLE_FILES, r2_client=client)

    # Nothing should be left indexed after a failed verification.
    index = backup_index.read_index(client)
    assert index["backups"] == []


def test_create_backup_size_mismatch_deletes_unverified_object():
    class _TamperedHeadClient(FakeR2Client):
        def head_object(self, key):
            info = super().head_object(key)
            info.size = info.size + 999  # simulate a corrupted/partial upload
            return info

    client = _TamperedHeadClient()
    with pytest.raises(BackupError):
        create_backup("manual", files=SAMPLE_FILES, r2_client=client)

    # The unverified object must have been cleaned up, and never indexed.
    assert client.list_objects("backups/") == []
    index = backup_index.read_index(client)
    assert index["backups"] == []


def test_create_backup_includes_extra_payload_without_polluting_files_dict():
    client = FakeR2Client()
    result = create_backup(
        "critical", files=SAMPLE_FILES, r2_client=client, reason="pre_season_close",
        extra_payload={"seasonName": "2025/26"},
    )
    assert result["fileCount"] == 3  # 2 real files + extra_payload.json
    assert "extra_payload.json" in result["manifestSha256"]


def test_create_backup_runs_retention_and_reports_it_in_the_result():
    client = FakeR2Client()
    retention_cfg = {"scheduled_max_count": 1, "manual_max_age_days": 90, "critical_max_count": None}

    first = create_backup("scheduled", files=SAMPLE_FILES, r2_client=client, retention_cfg=retention_cfg)
    second = create_backup("scheduled", files=SAMPLE_FILES, r2_client=client, retention_cfg=retention_cfg)

    # Cap of 1 scheduled backup — the first one must have been evicted by
    # the second creation's post-write retention sweep.
    assert "retention" in second
    evicted_ids = [e["id"] for e in second["retention"]["evicted"]]
    assert first["id"] in evicted_ids

    index = backup_index.read_index(client)
    assert [b["id"] for b in index["backups"]] == [second["id"]]


def test_create_backup_retention_failure_does_not_fail_the_backup_itself():
    # A retention sweep that itself raises (e.g. the index object becomes
    # unreadable for a reason other than "missing") must never take down an
    # otherwise-successful backup — "skip rather than fail"
    # (docs/01_Architecture.md §10). Simulated by making the index read
    # blow up with something other than R2ObjectNotFoundError, which
    # backup_index.read_index() does NOT already swallow.
    class _FlakyIndexClient(FakeR2Client):
        def __init__(self):
            super().__init__()
            self._index_reads = 0

        def get_object(self, key):
            if key == backup_index.INDEX_KEY:
                self._index_reads += 1
                # 1st read: add_entry() cataloguing the new backup — must
                # succeed, or the backup itself would fail. 2nd read: the
                # retention sweep's own read — this is the one that fails.
                if self._index_reads >= 2:
                    raise ConnectionError("simulated transient R2 read failure")
            return super().get_object(key)

    client = _FlakyIndexClient()
    result = create_backup("manual", files=SAMPLE_FILES, r2_client=client)

    assert result["id"] is not None  # the backup itself still succeeded
    assert "error" in result["retention"]
