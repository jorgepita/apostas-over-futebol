"""
tests/test_backup_restore.py

Coverage for src/backup/backup_restore.py — index rebuild from a raw R2
listing (never trusting backup_index.json alone), list/get/status,
validate_restore (dry-run), and restore() including its confirmation
requirement, pre-restore safety snapshot, and per-file write reporting.
See docs/09_Architecture_Decisions.md ADR-020.

Run with:  python -m pytest tests/test_backup_restore.py -v
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backup.backup_engine import create_backup
from src.backup.backup_restore import (
    RestoreError,
    get_backup_entry,
    get_recovery_status,
    list_backups,
    rebuild_index_from_r2,
    restore,
    validate_restore,
)
from src.backup.r2_client import FakeR2Client

SAMPLE_FILES = {"cloud_state.json": b'{"a": 1}', "picks_history.csv": b"Data;Liga\n"}


def _make_client_with_one_backup(backup_type="manual", extra_payload=None):
    client = FakeR2Client()
    result = create_backup(backup_type, files=SAMPLE_FILES, r2_client=client, extra_payload=extra_payload)
    return client, result


# ── rebuild_index_from_r2 / list / get ──────────────────────────────────────

def test_rebuild_index_from_r2_finds_backups_even_with_no_index_object():
    client, result = _make_client_with_one_backup()
    client.delete_object("backups/index.json")  # simulate the index itself being lost/corrupted

    rebuilt = rebuild_index_from_r2(client)
    assert any(b["id"] == result["id"] for b in rebuilt["backups"])


def test_list_backups_sorted_newest_first():
    client = FakeR2Client()
    r1 = create_backup("manual", files=SAMPLE_FILES, r2_client=client)
    r2 = create_backup("manual", files=SAMPLE_FILES, r2_client=client)

    backups = list_backups(client)
    ids = [b["id"] for b in backups]
    assert ids.index(r2["id"]) < ids.index(r1["id"])


def test_get_backup_entry_returns_none_for_unknown_id():
    client = FakeR2Client()
    assert get_backup_entry(client, "does-not-exist") is None


def test_get_recovery_status_reports_not_recoverable_when_empty():
    client = FakeR2Client()
    status = get_recovery_status(client)
    assert status["recoverable"] is False
    assert status["count"] == 0


def test_get_recovery_status_reports_latest_backup():
    client, result = _make_client_with_one_backup()
    status = get_recovery_status(client)
    assert status["recoverable"] is True
    assert status["latest"]["id"] == result["id"]


# ── validate_restore ─────────────────────────────────────────────────────────

def test_validate_restore_ok_for_healthy_backup():
    client, result = _make_client_with_one_backup()
    preview = validate_restore(client, result["id"])
    assert preview["ok"] is True
    assert preview["validation"]["status"] == "healthy"


def test_validate_restore_not_found_for_unknown_id():
    client = FakeR2Client()
    preview = validate_restore(client, "ghost")
    assert preview["ok"] is False
    assert preview["reason"] == "BACKUP_NOT_FOUND"


def test_validate_restore_flags_corrupted_archive():
    client, result = _make_client_with_one_backup()
    # Corrupt the object in place, keeping the same key/size roughly.
    client.put_object(result["key"], b"not a real zip file")
    preview = validate_restore(client, result["id"])
    assert preview["ok"] is False
    assert preview["reason"] == "BACKUP_CORRUPTED"


# ── restore() ────────────────────────────────────────────────────────────────

def test_restore_requires_confirmed_true():
    client, result = _make_client_with_one_backup()
    with pytest.raises(RestoreError):
        restore(client, result["id"], confirmed=False, write_file_fn=lambda *a: None)


def test_restore_refuses_corrupted_backup():
    client, result = _make_client_with_one_backup()
    client.put_object(result["key"], b"not a real zip file")
    with pytest.raises(RestoreError):
        restore(client, result["id"], confirmed=True, write_file_fn=lambda *a: None)


def test_restore_writes_every_archived_file_except_extra_payload():
    client, result = _make_client_with_one_backup(extra_payload={"seasonName": "x"})
    written_calls = []

    def fake_write(path, content_text, message):
        written_calls.append((path, content_text, message))

    outcome = restore(client, result["id"], confirmed=True, write_file_fn=fake_write)

    assert outcome["success"] is True
    assert set(outcome["written"]) == set(SAMPLE_FILES.keys())
    assert "extra_payload.json" not in outcome["written"]
    written_paths = {c[0] for c in written_calls}
    assert written_paths == set(SAMPLE_FILES.keys())
    for _path, _content, message in written_calls:
        assert result["id"] in message  # restore commits are traceable to their source backup


def test_restore_reports_per_file_failures_without_aborting_the_others():
    client, result = _make_client_with_one_backup()

    def flaky_write(path, content_text, message):
        if path == "cloud_state.json":
            raise RuntimeError("simulated GitHub write failure")

    outcome = restore(client, result["id"], confirmed=True, write_file_fn=flaky_write)
    assert outcome["success"] is False
    assert any(f["name"] == "cloud_state.json" for f in outcome["failed"])
    assert "picks_history.csv" in outcome["written"]


def test_restore_aborts_entirely_if_pre_restore_snapshot_fails():
    client, result = _make_client_with_one_backup()
    write_calls = []

    def snapshot_fn():
        raise RuntimeError("simulated snapshot failure")

    with pytest.raises(RestoreError):
        restore(client, result["id"], confirmed=True,
                write_file_fn=lambda *a: write_calls.append(a),
                pre_restore_snapshot_fn=snapshot_fn)

    assert write_calls == []  # nothing was written — the abort happened before any GitHub write


def test_restore_takes_pre_restore_snapshot_before_writing_files():
    client, result = _make_client_with_one_backup()
    call_order = []

    def snapshot_fn():
        call_order.append("snapshot")

    def write_fn(path, content_text, message):
        call_order.append(f"write:{path}")

    restore(client, result["id"], confirmed=True, write_file_fn=write_fn,
            pre_restore_snapshot_fn=snapshot_fn)

    assert call_order[0] == "snapshot"
    assert all(c.startswith("write:") for c in call_order[1:])
