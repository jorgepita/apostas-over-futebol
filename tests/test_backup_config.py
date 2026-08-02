"""
tests/test_backup_config.py

Coverage for src/backup/config.py — defensive fallback behaviour for
config.json["backup"] (mirroring src/config.py::get_void_policy()'s
per-key fallback style) and environment-sourced R2 settings.

Run with:  python -m pytest tests/test_backup_config.py -v
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backup.config import (
    DEFAULT_BACKUP_FILES,
    DEFAULT_MANUAL_MAX_AGE_DAYS,
    DEFAULT_SCHEDULED_MAX_COUNT,
    get_backup_config,
    get_r2_settings,
)


def test_get_backup_config_falls_back_to_defaults_when_config_missing(tmp_path):
    cfg = get_backup_config(base_path=tmp_path)  # no config.json at all in tmp_path
    assert cfg["enabled"] is True
    assert cfg["files"] == DEFAULT_BACKUP_FILES
    assert cfg["retention"]["scheduled_max_count"] == DEFAULT_SCHEDULED_MAX_COUNT
    assert cfg["retention"]["manual_max_age_days"] == DEFAULT_MANUAL_MAX_AGE_DAYS
    assert cfg["retention"]["critical_max_count"] is None


def test_get_backup_config_reads_real_config_json_from_project_root():
    # The real config.json (repo root) now has a "backup" block — this
    # confirms Phase 27.2's addition round-trips correctly through the
    # loader, using this project's real production config file.
    cfg = get_backup_config()
    assert cfg["enabled"] is True
    assert "cloud_state.json" in cfg["files"]
    assert cfg["retention"]["scheduled_max_count"] == 60


def test_get_backup_config_uses_custom_files_list(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({
        "backup": {"files": ["only_this.json"]}
    }))
    cfg = get_backup_config(base_path=tmp_path)
    assert cfg["files"] == ["only_this.json"]


def test_get_backup_config_falls_back_per_key_on_invalid_retention_values(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({
        "backup": {"retention": {"scheduled_max_count": -5, "manual_max_age_days": "not-a-number"}}
    }))
    cfg = get_backup_config(base_path=tmp_path)
    assert cfg["retention"]["scheduled_max_count"] == DEFAULT_SCHEDULED_MAX_COUNT
    assert cfg["retention"]["manual_max_age_days"] == DEFAULT_MANUAL_MAX_AGE_DAYS


def test_get_backup_config_disabled_flag_is_respected(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"backup": {"enabled": False}}))
    cfg = get_backup_config(base_path=tmp_path)
    assert cfg["enabled"] is False


def test_get_backup_config_survives_malformed_json(tmp_path):
    (tmp_path / "config.json").write_text("{not valid json")
    cfg = get_backup_config(base_path=tmp_path)
    assert cfg["files"] == DEFAULT_BACKUP_FILES  # falls back cleanly, does not raise


def test_get_r2_settings_reads_environment_variables(monkeypatch):
    monkeypatch.setenv("R2_ENABLED", "true")
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct1")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key1")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret1")
    monkeypatch.setenv("R2_BUCKET_NAME", "bucket1")

    settings = get_r2_settings()
    assert settings["enabled"] is True
    assert settings["account_id"] == "acct1"
    assert settings["access_key_id"] == "key1"
    assert settings["bucket"] == "bucket1"


def test_get_r2_settings_defaults_to_disabled_when_unset(monkeypatch):
    monkeypatch.delenv("R2_ENABLED", raising=False)
    settings = get_r2_settings()
    assert settings["enabled"] is False
