"""
tests/test_backup_integrity.py

Coverage for src/backup/backup_integrity.py::verify_remote_integrity() —
proactive R2 drift detection (HEAD-only), distinguishing a confirmed-missing
object from a transient check error, per docs/09_Architecture_Decisions.md
ADR-020 (following the basketball-over-bot precedent's own 404-vs-transient
distinction, deliberately carried over here).

Run with:  python -m pytest tests/test_backup_integrity.py -v
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backup.backup_engine import create_backup
from src.backup.backup_integrity import verify_remote_integrity
from src.backup.r2_client import FakeR2Client

SAMPLE_FILES = {"cloud_state.json": b'{"a": 1}'}


def test_verify_remote_integrity_all_healthy():
    client = FakeR2Client()
    create_backup("manual", files=SAMPLE_FILES, r2_client=client)
    create_backup("scheduled", files=SAMPLE_FILES, r2_client=client)

    report = verify_remote_integrity(client)
    assert report["totalChecked"] == 2
    assert report["healthyCount"] == 2
    assert report["missing"] == []
    assert report["errors"] == []


def test_verify_remote_integrity_detects_out_of_band_deletion():
    client = FakeR2Client()
    result = create_backup("manual", files=SAMPLE_FILES, r2_client=client)
    client._external_delete(result["key"])  # simulates an operator deleting it in the R2 console

    report = verify_remote_integrity(client)
    assert report["healthyCount"] == 0
    assert len(report["missing"]) == 1
    assert report["missing"][0]["id"] == result["id"]
    assert report["missing"][0]["checkReason"] == "not_found"


def test_verify_remote_integrity_detects_size_mismatch():
    client = FakeR2Client()
    result = create_backup("manual", files=SAMPLE_FILES, r2_client=client)
    client._store[result["key"]] = b"short"  # replace with different-sized content, same key

    report = verify_remote_integrity(client)
    assert len(report["missing"]) == 1
    assert report["missing"][0]["checkReason"] == "size_mismatch"


def test_verify_remote_integrity_keeps_transient_errors_separate_from_confirmed_missing():
    class _FlakyHeadClient(FakeR2Client):
        def head_object(self, key):
            raise TimeoutError("simulated transient network error")

    client = _FlakyHeadClient()
    client.put_object("backups/manual/x.zip", b"data")
    from src.backup import backup_index
    backup_index.add_entry(client, {"id": "x", "type": "manual", "key": "backups/manual/x.zip",
                                     "sizeBytes": 4, "createdAt": "2026-01-01T00:00:00+00:00"})

    report = verify_remote_integrity(client)
    assert report["missing"] == []  # a network blip must never be reported as confirmed data loss
    assert len(report["errors"]) == 1


def test_verify_remote_integrity_with_no_backups_is_a_clean_no_op():
    client = FakeR2Client()
    report = verify_remote_integrity(client)
    assert report == {"totalChecked": 0, "healthyCount": 0, "missing": [], "errors": []}
