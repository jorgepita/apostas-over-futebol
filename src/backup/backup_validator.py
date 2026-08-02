"""
src/backup/backup_validator.py

Manifest construction, SHA-256 integrity metadata, and archive validation —
the single implementation used by both backup creation (compute manifest)
and restore/integrity-checking (verify manifest against archive contents)
so the two can never silently disagree about what "valid" means. See
docs/09_Architecture_Decisions.md ADR-020.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

MANIFEST_ENTRY = "manifest.json"
REQUIRED_MANIFEST_FIELDS = ("id", "createdAt", "backupType", "files", "fileCount", "totalBytes")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_manifest(backup_id: str, backup_type: str, files: dict[str, bytes], *,
                    reason: str | None = None, github_commit_sha: str | None = None) -> dict:
    file_entries = []
    total_bytes = 0
    for name, content in files.items():
        size = len(content)
        total_bytes += size
        file_entries.append({"name": name, "sizeBytes": size, "sha256": sha256_hex(content)})
    return {
        "id": backup_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "backupType": backup_type,
        "reason": reason,
        "githubCommitSha": github_commit_sha,
        "files": file_entries,
        "fileCount": len(file_entries),
        "totalBytes": total_bytes,
        "version": 1,
    }


def build_archive(backup_id: str, backup_type: str, files: dict[str, bytes], *,
                   reason: str | None = None, github_commit_sha: str | None = None,
                   extra_payload: dict | None = None) -> tuple[bytes, dict]:
    """Builds one ZIP archive fully in memory. Returns (zip_bytes, manifest).
    Never touches disk — this dataset (~450 KB uncompressed as of the Phase
    27.1 audit) comfortably fits in memory end to end, so no temp file is
    structurally required (see ADR-020's "zero bytes at rest on Railway"
    principle)."""
    files_to_archive = dict(files)
    if extra_payload:
        # e.g. the dashboard's Season Archive object, captured verbatim
        # alongside the GitHub-sourced files for a pre-End-of-Season
        # critical backup — see docs/03_Dashboard.md's Season Archive
        # section and docs/09_Architecture_Decisions.md ADR-020.
        payload_bytes = json.dumps(extra_payload, ensure_ascii=False, indent=2).encode("utf-8")
        files_to_archive["extra_payload.json"] = payload_bytes

    manifest = build_manifest(backup_id, backup_type, files_to_archive, reason=reason,
                               github_commit_sha=github_commit_sha)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files_to_archive.items():
            zf.writestr(name, content)
        zf.writestr(MANIFEST_ENTRY, json.dumps(manifest, ensure_ascii=False, indent=2))
    return buf.getvalue(), manifest


def validate_archive(zip_bytes: bytes) -> dict:
    """Returns {status: 'healthy'|'warning'|'corrupted', issues: [...], manifest: {...}|None}.
    Never raises — a validation failure is data, not an exception, so callers
    (restore, integrity sweep) can always inspect the result rather than
    needing a try/except around every call site."""
    issues: list[str] = []

    try:
        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, mode="r") as zf:
            bad_entry = zf.testzip()
            if bad_entry is not None:
                return {"status": "corrupted", "issues": [f"corrupt ZIP entry: {bad_entry}"], "manifest": None}

            names = set(zf.namelist())
            if MANIFEST_ENTRY not in names:
                return {"status": "corrupted", "issues": ["manifest.json missing from archive"], "manifest": None}

            try:
                manifest = json.loads(zf.read(MANIFEST_ENTRY).decode("utf-8"))
            except Exception as e:
                return {"status": "corrupted", "issues": [f"manifest.json unparseable: {e}"], "manifest": None}

            missing_fields = [f for f in REQUIRED_MANIFEST_FIELDS if f not in manifest]
            if missing_fields:
                return {"status": "corrupted",
                        "issues": [f"manifest.json missing required fields: {missing_fields}"],
                        "manifest": manifest}

            for entry in manifest.get("files", []):
                name = entry.get("name")
                expected_sha = entry.get("sha256")
                if name not in names:
                    issues.append(f"file listed in manifest but missing from archive: {name}")
                    continue
                actual_bytes = zf.read(name)
                actual_sha = sha256_hex(actual_bytes)
                if expected_sha and actual_sha != expected_sha:
                    issues.append(f"checksum mismatch for {name}: expected {expected_sha}, got {actual_sha}")

    except zipfile.BadZipFile as e:
        return {"status": "corrupted", "issues": [f"not a valid ZIP: {e}"], "manifest": None}
    except Exception as e:
        return {"status": "corrupted", "issues": [f"unexpected validation error: {e}"], "manifest": None}

    is_corrupted = any("checksum mismatch" in i or "missing from archive" in i for i in issues)
    status = "corrupted" if is_corrupted else ("warning" if issues else "healthy")
    return {"status": status, "issues": issues, "manifest": manifest}


def extract_files(zip_bytes: bytes) -> dict[str, bytes]:
    """Returns {filename: bytes} for every archive member except manifest.json."""
    out: dict[str, bytes] = {}
    buf = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(buf, mode="r") as zf:
        for name in zf.namelist():
            if name == MANIFEST_ENTRY:
                continue
            out[name] = zf.read(name)
    return out
