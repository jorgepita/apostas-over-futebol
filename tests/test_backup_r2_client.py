"""
tests/test_backup_r2_client.py

Coverage for src/backup/r2_client.py — the FakeR2Client double used
throughout this suite (put/get/head/delete/list, fault injection), plus
get_r2_client()'s fail-closed behaviour when R2 is disabled or
misconfigured, and a construction-only smoke test for the real R2Client
class (boto3 is installed in this environment — see the Phase 27.2
handover — but no real Cloudflare R2 bucket/credentials exist, so this
intentionally never performs a real network call; boto3.client()
construction alone does not require network access).

Run with:  python -m pytest tests/test_backup_r2_client.py -v
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backup.r2_client import (
    FakeR2Client,
    R2Client,
    R2NotConfiguredError,
    R2ObjectNotFoundError,
    get_r2_client,
)


# ── FakeR2Client ─────────────────────────────────────────────────────────────

def test_fake_r2_put_then_get_round_trips():
    client = FakeR2Client()
    client.put_object("backups/manual/x.zip", b"hello world")
    assert client.get_object("backups/manual/x.zip") == b"hello world"


def test_fake_r2_head_object_reports_correct_size():
    client = FakeR2Client()
    client.put_object("backups/manual/x.zip", b"12345")
    info = client.head_object("backups/manual/x.zip")
    assert info.size == 5
    assert info.key == "backups/manual/x.zip"


def test_fake_r2_head_missing_object_raises_not_found():
    client = FakeR2Client()
    with pytest.raises(R2ObjectNotFoundError):
        client.head_object("backups/manual/missing.zip")


def test_fake_r2_get_missing_object_raises_not_found():
    client = FakeR2Client()
    with pytest.raises(R2ObjectNotFoundError):
        client.get_object("backups/manual/missing.zip")


def test_fake_r2_delete_object_is_idempotent():
    client = FakeR2Client()
    client.put_object("backups/manual/x.zip", b"data")
    client.delete_object("backups/manual/x.zip")
    client.delete_object("backups/manual/x.zip")  # no error on second delete
    with pytest.raises(R2ObjectNotFoundError):
        client.get_object("backups/manual/x.zip")


def test_fake_r2_list_objects_filters_by_prefix():
    client = FakeR2Client()
    client.put_object("backups/scheduled/a.zip", b"1")
    client.put_object("backups/manual/b.zip", b"22")
    client.put_object("other/c.txt", b"333")

    all_backups = client.list_objects("backups/")
    keys = {o.key for o in all_backups}
    assert keys == {"backups/scheduled/a.zip", "backups/manual/b.zip"}

    scheduled_only = client.list_objects("backups/scheduled/")
    assert [o.key for o in scheduled_only] == ["backups/scheduled/a.zip"]


def test_fake_r2_fail_next_put_injects_one_shot_failure():
    client = FakeR2Client()
    client.fail_next_put = True
    with pytest.raises(RuntimeError):
        client.put_object("backups/manual/x.zip", b"data")
    # The flag is one-shot — the next call succeeds normally.
    client.put_object("backups/manual/x.zip", b"data")
    assert client.get_object("backups/manual/x.zip") == b"data"


def test_fake_r2_fail_next_head_injects_one_shot_failure():
    client = FakeR2Client()
    client.put_object("backups/manual/x.zip", b"data")
    client.fail_next_head = True
    with pytest.raises(RuntimeError):
        client.head_object("backups/manual/x.zip")
    client.head_object("backups/manual/x.zip")  # succeeds the second time


def test_fake_r2_external_delete_simulates_out_of_band_drift():
    client = FakeR2Client()
    client.put_object("backups/manual/x.zip", b"data")
    client._external_delete("backups/manual/x.zip")
    with pytest.raises(R2ObjectNotFoundError):
        client.head_object("backups/manual/x.zip")


# ── get_r2_client() fail-closed behaviour ───────────────────────────────────

def test_get_r2_client_raises_when_disabled():
    with pytest.raises(R2NotConfiguredError):
        get_r2_client({"enabled": False})


def test_get_r2_client_raises_when_credentials_incomplete():
    with pytest.raises(R2NotConfiguredError):
        get_r2_client({
            "enabled": True,
            "account_id": "acct123",
            "access_key_id": "",  # missing
            "secret_access_key": "secret",
            "bucket": "my-bucket",
        })


def test_get_r2_client_builds_real_client_when_fully_configured():
    # Construction-only — no network call is made by boto3.client(); this
    # confirms the real R2Client wiring is correct without needing a real
    # Cloudflare R2 bucket, which does not exist in this environment.
    client = get_r2_client({
        "enabled": True,
        "account_id": "test-account",
        "endpoint_url": "",
        "access_key_id": "AKIAFAKE",
        "secret_access_key": "fake-secret",
        "bucket": "test-bucket",
    })
    assert isinstance(client, R2Client)


def test_get_r2_client_prefers_explicit_endpoint_url_over_account_id():
    client = get_r2_client({
        "enabled": True,
        "account_id": "",
        "endpoint_url": "https://example-r2-endpoint.example.com",
        "access_key_id": "AKIAFAKE",
        "secret_access_key": "fake-secret",
        "bucket": "test-bucket",
    })
    assert isinstance(client, R2Client)
