"""
tests/test_backup_endpoints.py

Coverage for sync_server.py's Phase 27.2 backup endpoints (/backup/status,
/backup/create, /backup/validate-restore, /backup/restore) using Flask's
test client — no real network, no real GitHub, no real R2. Every backup
module used by these endpoints is imported lazily inside the request
handler (matching this file's existing /run-settlement convention), so
monkeypatching the underlying src.backup.* module attributes is picked up
on every request.

GITHUB_TOKEN must be set before importing sync_server.py — it raises at
import time otherwise (existing, pre-Phase-27.2 behaviour, unrelated to
this phase) — so this is set directly in os.environ at module load time,
before the import, rather than via a per-test monkeypatch fixture.

Run with:  python -m pytest tests/test_backup_endpoints.py -v
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("GITHUB_TOKEN", "test-token-for-sync-server-import")

import pytest

import sync_server
from src.backup import backup_index, github_files, r2_client
from src.backup.backup_engine import create_backup as engine_create_backup
from src.backup.r2_client import FakeR2Client, R2NotConfiguredError


@pytest.fixture
def client():
    sync_server.app.config["TESTING"] = True
    return sync_server.app.test_client()


@pytest.fixture
def fake_r2(monkeypatch):
    fc = FakeR2Client()
    monkeypatch.setattr(r2_client, "get_r2_client", lambda settings=None: fc)
    return fc


def _disable_r2(monkeypatch):
    def _raise(settings=None):
        raise R2NotConfiguredError("R2_ENABLED is not set to true")
    monkeypatch.setattr(r2_client, "get_r2_client", _raise)


# ── GET /backup/status ──────────────────────────────────────────────────────

def test_status_reports_not_configured_when_r2_disabled(client, monkeypatch):
    _disable_r2(monkeypatch)
    resp = client.get("/backup/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["r2Configured"] is False
    assert body["backups"] == []


def test_status_lists_existing_backups_when_r2_configured(client, fake_r2):
    engine_create_backup("manual", files={"cloud_state.json": b"{}"}, r2_client=fake_r2)
    resp = client.get("/backup/status")
    body = resp.get_json()
    assert body["r2Configured"] is True
    assert len(body["backups"]) == 1
    assert body["recovery"]["recoverable"] is True


def test_status_with_verify_param_runs_integrity_check(client, fake_r2):
    result = engine_create_backup("manual", files={"cloud_state.json": b"{}"}, r2_client=fake_r2)
    resp = client.get("/backup/status?verify=1")
    body = resp.get_json()
    assert body["integrity"]["totalChecked"] == 1
    assert body["integrity"]["healthyCount"] == 1


# ── POST /backup/create ──────────────────────────────────────────────────────

def test_create_rejects_scheduled_type(client, fake_r2):
    resp = client.post("/backup/create", json={"type": "scheduled"})
    assert resp.status_code == 400
    assert "scheduled" in resp.get_json()["error"]


def test_create_returns_503_when_r2_not_configured(client, monkeypatch):
    _disable_r2(monkeypatch)
    resp = client.post("/backup/create", json={"type": "manual"})
    assert resp.status_code == 503


def test_create_manual_backup_fetches_files_from_github_and_uploads(client, fake_r2, monkeypatch):
    monkeypatch.setattr(github_files, "fetch_files",
                         lambda paths: {"cloud_state.json": b'{"ok": true}'})
    monkeypatch.setattr(github_files, "fetch_commit_sha", lambda path: "deadbeef")

    resp = client.post("/backup/create", json={"type": "manual", "reason": "test"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["backup"]["type"] == "manual"
    assert body["backup"]["githubCommitSha"] == "deadbeef"

    # Actually landed in R2, not just claimed by the response.
    assert len(fake_r2.list_objects("backups/manual/")) == 1


def test_create_critical_backup_includes_extra_payload(client, fake_r2, monkeypatch):
    monkeypatch.setattr(github_files, "fetch_files",
                         lambda paths: {"cloud_state.json": b"{}"})
    monkeypatch.setattr(github_files, "fetch_commit_sha", lambda path: None)

    resp = client.post("/backup/create", json={
        "type": "critical", "reason": "pre_season_close",
        "extraPayload": {"seasonName": "2025/26"},
    })
    body = resp.get_json()
    assert body["success"] is True
    assert "extra_payload.json" in body["backup"]["manifestSha256"]


def test_create_returns_500_when_github_has_no_files(client, fake_r2, monkeypatch):
    monkeypatch.setattr(github_files, "fetch_files", lambda paths: {})
    monkeypatch.setattr(github_files, "fetch_commit_sha", lambda path: None)
    resp = client.post("/backup/create", json={"type": "manual"})
    assert resp.status_code == 500


# ── POST /backup/validate-restore ────────────────────────────────────────────

def test_validate_restore_requires_id(client, fake_r2):
    resp = client.post("/backup/validate-restore", json={})
    assert resp.status_code == 400


def test_validate_restore_reports_ok_for_healthy_backup(client, fake_r2):
    result = engine_create_backup("manual", files={"cloud_state.json": b"{}"}, r2_client=fake_r2)
    resp = client.post("/backup/validate-restore", json={"id": result["id"]})
    body = resp.get_json()
    assert body["ok"] is True


def test_validate_restore_reports_not_found(client, fake_r2):
    resp = client.post("/backup/validate-restore", json={"id": "ghost"})
    body = resp.get_json()
    assert body["ok"] is False
    assert body["reason"] == "BACKUP_NOT_FOUND"


# ── POST /backup/restore ─────────────────────────────────────────────────────

def test_restore_requires_id(client, fake_r2):
    resp = client.post("/backup/restore", json={"confirmed": True})
    assert resp.status_code == 400


def test_restore_without_confirmed_is_rejected(client, fake_r2):
    result = engine_create_backup("manual", files={"cloud_state.json": b"{}"}, r2_client=fake_r2)
    resp = client.post("/backup/restore", json={"id": result["id"]})
    assert resp.status_code == 400


def test_restore_writes_files_back_to_github_and_takes_pre_restore_snapshot(client, fake_r2, monkeypatch):
    result = engine_create_backup("manual", files={"cloud_state.json": b'{"restored": true}'},
                                   r2_client=fake_r2)

    written = []
    monkeypatch.setattr(github_files, "write_file",
                         lambda path, content, message: written.append((path, content, message)))
    monkeypatch.setattr(github_files, "fetch_files",
                         lambda paths: {"cloud_state.json": b'{"current": true}'})

    resp = client.post("/backup/restore", json={"id": result["id"], "confirmed": True})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert ("cloud_state.json", '{"restored": true}') in [(w[0], w[1]) for w in written]

    # The mandatory pre-restore safety snapshot must have created a second,
    # independent 'critical' backup before the restore write happened.
    critical_backups = fake_r2.list_objects("backups/critical/")
    assert len(critical_backups) == 1


def test_restore_returns_400_for_corrupted_backup(client, fake_r2, monkeypatch):
    result = engine_create_backup("manual", files={"cloud_state.json": b"{}"}, r2_client=fake_r2)
    fake_r2.put_object(result["key"], b"not a real zip")
    monkeypatch.setattr(github_files, "write_file", lambda *a: None)

    resp = client.post("/backup/restore", json={"id": result["id"], "confirmed": True})
    assert resp.status_code == 400


# ── Phase 27.3: production-hardening error paths ────────────────────────────

def test_status_returns_not_configured_when_r2_client_construction_raises_unexpectedly(client, monkeypatch):
    # Distinct from the R2NotConfiguredError case above — this simulates
    # R2Client's own construction failing for some other reason (e.g. a
    # malformed region reaching botocore's validation). Must still produce
    # the same clean, non-crashing "not configured" shape, not an
    # unhandled 500.
    def _raise(settings=None):
        raise RuntimeError("simulated unexpected construction failure")
    monkeypatch.setattr(r2_client, "get_r2_client", _raise)

    resp = client.get("/backup/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["r2Configured"] is False


def test_create_returns_503_when_r2_client_construction_raises_unexpectedly(client, monkeypatch):
    def _raise(settings=None):
        raise RuntimeError("simulated unexpected construction failure")
    monkeypatch.setattr(r2_client, "get_r2_client", _raise)

    resp = client.post("/backup/create", json={"type": "manual"})
    assert resp.status_code == 503
    assert "error" in resp.get_json()


def test_create_returns_clean_json_error_when_r2_operation_is_permission_denied(client, monkeypatch):
    from src.backup.r2_client import R2PermissionError

    class _DeniedClient:
        def put_object(self, key, body):
            raise R2PermissionError("R2 put_object backups/manual/x.zip: access denied by R2 (code='AccessDenied')")

    monkeypatch.setattr(r2_client, "get_r2_client", lambda settings=None: _DeniedClient())
    monkeypatch.setattr(github_files, "fetch_files", lambda paths: {"cloud_state.json": b"{}"})
    monkeypatch.setattr(github_files, "fetch_commit_sha", lambda path: None)

    resp = client.post("/backup/create", json={"type": "manual"})
    assert resp.status_code == 500
    body = resp.get_json()
    assert "error" in body
    assert "access denied" in body["error"].lower()


def test_validate_restore_returns_clean_json_error_on_unexpected_r2_failure(client, monkeypatch):
    from src.backup.r2_client import R2ConnectionError

    class _UnreachableClient:
        def list_objects(self, prefix):
            raise R2ConnectionError("R2 list_objects backups/: could not reach the R2 endpoint")

    monkeypatch.setattr(r2_client, "get_r2_client", lambda settings=None: _UnreachableClient())

    resp = client.post("/backup/validate-restore", json={"id": "any-id"})
    assert resp.status_code == 500
    assert "error" in resp.get_json()
