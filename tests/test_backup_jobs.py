"""
tests/test_backup_jobs.py

Coverage for the two GitHub Actions entry-point scripts, backup_job.py
(scheduled backup creation) and backup_integrity_job.py (weekly R2
integrity sweep) — both must be safe to run in an environment where R2
isn't configured yet (this repository's current state, see the Phase 27.2
handover), never failing the wider bot.yml workflow over that alone.

Run with:  python -m pytest tests/test_backup_jobs.py -v
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import backup_integrity_job
import backup_job
from src.backup.r2_client import FakeR2Client, R2NotConfiguredError


# ── backup_job.py ────────────────────────────────────────────────────────────

def test_backup_job_exits_zero_when_r2_not_configured(monkeypatch):
    def fake_get_r2_client(settings):
        raise R2NotConfiguredError("not configured")

    monkeypatch.setattr(backup_job, "get_r2_client", fake_get_r2_client)
    assert backup_job.main() == 0


def test_backup_job_exits_zero_when_disabled_in_config(monkeypatch):
    monkeypatch.setattr(backup_job, "get_backup_config", lambda: {
        "enabled": False, "files": [], "retention": {},
    })
    assert backup_job.main() == 0


def test_backup_job_creates_a_scheduled_backup_from_real_repo_files(monkeypatch, tmp_path):
    fake_client = FakeR2Client()
    monkeypatch.setattr(backup_job, "get_r2_client", lambda settings: fake_client)

    # Point BASE at a throwaway directory with one real-shaped file, so this
    # test never reads or depends on the actual production cloud_state.json.
    (tmp_path / "cloud_state.json").write_text('{"test": true}')
    monkeypatch.setattr(backup_job, "BASE", tmp_path)
    monkeypatch.setattr(backup_job, "get_backup_config", lambda: {
        "enabled": True, "files": ["cloud_state.json", "does_not_exist.csv"],
        "retention": {"scheduled_max_count": 60, "manual_max_age_days": 90, "critical_max_count": None},
    })

    assert backup_job.main() == 0
    objects = fake_client.list_objects("backups/scheduled/")
    assert len(objects) == 1


def test_backup_job_exits_zero_when_no_files_found(monkeypatch, tmp_path):
    fake_client = FakeR2Client()
    monkeypatch.setattr(backup_job, "get_r2_client", lambda settings: fake_client)
    monkeypatch.setattr(backup_job, "BASE", tmp_path)  # empty directory
    monkeypatch.setattr(backup_job, "get_backup_config", lambda: {
        "enabled": True, "files": ["nothing_here.json"], "retention": {},
    })
    assert backup_job.main() == 0
    assert fake_client.list_objects("backups/") == []


# ── backup_integrity_job.py ──────────────────────────────────────────────────

def test_integrity_job_exits_zero_when_r2_not_configured(monkeypatch):
    def fake_get_r2_client(settings):
        raise R2NotConfiguredError("not configured")

    monkeypatch.setattr(backup_integrity_job, "get_r2_client", fake_get_r2_client)
    assert backup_integrity_job.main() == 0


def test_integrity_job_exits_zero_when_all_healthy(monkeypatch):
    fake_client = FakeR2Client()
    from src.backup.backup_engine import create_backup
    create_backup("manual", files={"cloud_state.json": b"{}"}, r2_client=fake_client)

    monkeypatch.setattr(backup_integrity_job, "get_r2_client", lambda settings: fake_client)
    assert backup_integrity_job.main() == 0


def test_integrity_job_exits_nonzero_when_a_backup_is_confirmed_missing(monkeypatch):
    fake_client = FakeR2Client()
    from src.backup.backup_engine import create_backup
    result = create_backup("manual", files={"cloud_state.json": b"{}"}, r2_client=fake_client)
    fake_client._external_delete(result["key"])

    monkeypatch.setattr(backup_integrity_job, "get_r2_client", lambda settings: fake_client)
    assert backup_integrity_job.main() == 1
