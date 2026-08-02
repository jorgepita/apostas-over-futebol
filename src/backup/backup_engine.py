"""
src/backup/backup_engine.py

Creates one backup: build ZIP in memory -> upload to R2 -> HEAD-verify ->
record in the R2 index -> run retention. Every step that can fail leaves
nothing behind (see docs/09_Architecture_Decisions.md ADR-020's "fail
closed, nothing partial is ever durably recorded" principle). No file is
ever written to Railway's (or a GitHub Actions runner's) local disk by this
module — everything is an in-memory bytes object, which comfortably fits
this dataset's size (~450 KB uncompressed as of the Phase 27.1 audit).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.backup import backup_index
from src.backup.backup_validator import build_archive

VALID_TYPES = ("scheduled", "critical", "manual")


class BackupError(RuntimeError):
    """Raised when a backup cannot be created — the caller decides how to
    surface it (log + non-fatal exit for the scheduled job, HTTP 500 for a
    Railway endpoint). Creating a backup never raises anything that could
    be mistaken for a production-data write failure — GitHub itself is
    never touched by this function."""


def _make_backup_id(backup_type: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%f")[:-3]
    return f"{ts}-{backup_type}-{uuid.uuid4().hex[:8]}"


def _object_key(backup_id: str, backup_type: str) -> str:
    return f"backups/{backup_type}/{backup_id}.zip"


def create_backup(backup_type: str, *, files: dict[str, bytes], r2_client, reason: str | None = None,
                   github_commit_sha: str | None = None, extra_payload: dict | None = None,
                   run_retention: bool = True, retention_cfg: dict | None = None) -> dict:
    """Creates and uploads one backup archive.

    `files` must already be provided by the caller as {filename: bytes} —
    this function has no opinion on WHERE they came from (disk, for the
    GitHub Actions job; the GitHub Contents API, for Railway's on-demand
    endpoints — see github_files.py / backup_job.py for the two real
    sources). Keeping the fetch outside this function is what lets one
    engine serve both callers without duplicating GitHub-access logic.
    """
    if backup_type not in VALID_TYPES:
        raise BackupError(f"invalid backup type: {backup_type!r} (must be one of {VALID_TYPES})")
    if not files:
        raise BackupError("no files provided to back up — refusing to create an empty archive")

    backup_id = _make_backup_id(backup_type)
    zip_bytes, manifest = build_archive(
        backup_id, backup_type, files, reason=reason,
        github_commit_sha=github_commit_sha, extra_payload=extra_payload,
    )
    key = _object_key(backup_id, backup_type)

    try:
        r2_client.put_object(key, zip_bytes)
    except Exception as e:
        raise BackupError(f"R2 upload failed for backup {backup_id}: {e}") from e

    try:
        info = r2_client.head_object(key)
    except Exception as e:
        raise BackupError(f"R2 upload for backup {backup_id} could not be verified: {e}") from e

    if info.size != len(zip_bytes):
        try:
            r2_client.delete_object(key)  # best-effort cleanup of the unverified object
        except Exception:
            pass
        raise BackupError(
            f"R2 upload for backup {backup_id} failed verification: "
            f"expected {len(zip_bytes)} bytes, R2 reports {info.size}"
        )

    entry = {
        "id": backup_id,
        "type": backup_type,
        "key": key,
        "createdAt": manifest["createdAt"],
        "reason": reason,
        "sizeBytes": len(zip_bytes),
        "fileCount": manifest["fileCount"],
        "githubCommitSha": github_commit_sha,
        "manifestSha256": {f["name"]: f["sha256"] for f in manifest["files"]},
    }
    backup_index.add_entry(r2_client, entry)

    result = dict(entry)
    if run_retention:
        from src.backup.backup_retention import run_retention as _run_retention
        from src.backup.config import get_backup_config
        cfg = retention_cfg if retention_cfg is not None else get_backup_config()["retention"]
        try:
            result["retention"] = _run_retention(r2_client, cfg)
        except Exception as e:
            # Retention never blocks a successful backup — same "skip
            # rather than fail" principle this project already applies to
            # settlement (docs/01_Architecture.md §10).
            result["retention"] = {"error": str(e)}

    return result
