"""
tests/test_backup_index.py

Coverage for src/backup/backup_index.py — the R2-hosted backup catalog
(read/add/remove entry), including its documented tolerance for a missing
or corrupted index object (see the module's own docstring on why this is
acceptable given rebuild_index_from_r2() always exists as ground truth).

Run with:  python -m pytest tests/test_backup_index.py -v
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backup import backup_index
from src.backup.r2_client import FakeR2Client


def test_read_index_returns_empty_shape_when_not_yet_created():
    client = FakeR2Client()
    index = backup_index.read_index(client)
    assert index == {"updatedAt": None, "backups": []}


def test_add_entry_then_read_index_round_trips():
    client = FakeR2Client()
    entry = {"id": "b1", "type": "manual", "key": "backups/manual/b1.zip"}
    backup_index.add_entry(client, entry)

    index = backup_index.read_index(client)
    assert len(index["backups"]) == 1
    assert index["backups"][0]["id"] == "b1"
    assert index["updatedAt"] is not None


def test_add_entry_replaces_existing_entry_with_same_id():
    client = FakeR2Client()
    backup_index.add_entry(client, {"id": "b1", "sizeBytes": 100})
    backup_index.add_entry(client, {"id": "b1", "sizeBytes": 200})

    index = backup_index.read_index(client)
    assert len(index["backups"]) == 1
    assert index["backups"][0]["sizeBytes"] == 200


def test_remove_entry_deletes_only_the_matching_id():
    client = FakeR2Client()
    backup_index.add_entry(client, {"id": "b1"})
    backup_index.add_entry(client, {"id": "b2"})
    backup_index.remove_entry(client, "b1")

    index = backup_index.read_index(client)
    assert [b["id"] for b in index["backups"]] == ["b2"]


def test_read_index_tolerates_corrupted_index_object():
    client = FakeR2Client()
    client.put_object(backup_index.INDEX_KEY, b"{not valid json at all")
    index = backup_index.read_index(client)
    assert index == {"updatedAt": None, "backups": []}


def test_read_index_tolerates_index_object_with_wrong_shape():
    client = FakeR2Client()
    client.put_object(backup_index.INDEX_KEY, b'{"backups": "not-a-list"}')
    index = backup_index.read_index(client)
    assert index == {"updatedAt": None, "backups": []}
