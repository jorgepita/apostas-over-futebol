"""
tests/test_backup_validator.py

Coverage for src/backup/backup_validator.py — manifest construction,
in-memory ZIP archive build, and validation (structure, required manifest
fields, per-file SHA-256 integrity). See docs/09_Architecture_Decisions.md
ADR-020.

Run with:  python -m pytest tests/test_backup_validator.py -v
"""
import sys
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backup.backup_validator import (
    build_archive,
    build_manifest,
    extract_files,
    sha256_hex,
    validate_archive,
)


def _sample_files():
    return {
        "cloud_state.json": b'{"a": 1}',
        "picks_history.csv": b"Data;Liga;Jogo\n2026-08-01;premier;Team A vs Team B\n",
    }


# ── build_manifest ───────────────────────────────────────────────────────────

def test_build_manifest_has_required_fields_and_correct_checksums():
    files = _sample_files()
    manifest = build_manifest("id1", "manual", files, reason="test", github_commit_sha="abc123")

    assert manifest["id"] == "id1"
    assert manifest["backupType"] == "manual"
    assert manifest["reason"] == "test"
    assert manifest["githubCommitSha"] == "abc123"
    assert manifest["fileCount"] == 2
    assert manifest["totalBytes"] == sum(len(v) for v in files.values())

    by_name = {f["name"]: f for f in manifest["files"]}
    for name, content in files.items():
        assert by_name[name]["sha256"] == sha256_hex(content)
        assert by_name[name]["sizeBytes"] == len(content)


# ── build_archive / validate_archive round trip ─────────────────────────────

def test_build_archive_round_trips_cleanly_through_validate_archive():
    zip_bytes, manifest = build_archive("id2", "scheduled", _sample_files())
    result = validate_archive(zip_bytes)

    assert result["status"] == "healthy"
    assert result["issues"] == []
    assert result["manifest"]["id"] == manifest["id"]


def test_build_archive_includes_extra_payload_and_it_survives_validation():
    payload = {"seasonName": "2025/26", "financial": {"pnl": 123.45}}
    zip_bytes, manifest = build_archive("id3", "critical", _sample_files(), extra_payload=payload)

    names = [f["name"] for f in manifest["files"]]
    assert "extra_payload.json" in names

    files = extract_files(zip_bytes)
    assert "extra_payload.json" in files
    import json
    assert json.loads(files["extra_payload.json"]) == payload


def test_extract_files_excludes_manifest_entry():
    zip_bytes, _manifest = build_archive("id4", "manual", _sample_files())
    files = extract_files(zip_bytes)
    assert "manifest.json" not in files
    assert set(files.keys()) == set(_sample_files().keys())


# ── validate_archive failure modes ──────────────────────────────────────────

def test_validate_archive_rejects_non_zip_bytes():
    result = validate_archive(b"not a zip file at all")
    assert result["status"] == "corrupted"
    assert result["manifest"] is None


def test_validate_archive_rejects_zip_missing_manifest():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("cloud_state.json", b"{}")
    result = validate_archive(buf.getvalue())
    assert result["status"] == "corrupted"
    assert any("manifest.json missing" in i for i in result["issues"])


def test_validate_archive_rejects_manifest_missing_required_fields():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", '{"id": "x"}')
    result = validate_archive(buf.getvalue())
    assert result["status"] == "corrupted"
    assert any("missing required fields" in i for i in result["issues"])


def test_validate_archive_detects_tampered_file_checksum_mismatch():
    zip_bytes, _manifest = build_archive("id5", "manual", _sample_files())

    # Tamper: rewrite one archive member's content without touching the
    # manifest's recorded checksum — simulates corruption in transit/storage.
    buf_in = BytesIO(zip_bytes)
    buf_out = BytesIO()
    with zipfile.ZipFile(buf_in, "r") as zin, zipfile.ZipFile(buf_out, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "cloud_state.json":
                data = b'{"a": 999999}'  # different content, same manifest checksum
            zout.writestr(item, data)

    result = validate_archive(buf_out.getvalue())
    assert result["status"] == "corrupted"
    assert any("checksum mismatch" in i for i in result["issues"])


def test_validate_archive_flags_file_listed_but_missing_from_archive():
    # Build a manifest that references a file, then a ZIP that never
    # actually contains it — simulates a partial/interrupted archive.
    import json
    manifest = build_manifest("id6", "manual", {"ghost.csv": b"x"})
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        # deliberately never write ghost.csv
    result = validate_archive(buf.getvalue())
    assert result["status"] == "corrupted"
    assert any("missing from archive" in i for i in result["issues"])
