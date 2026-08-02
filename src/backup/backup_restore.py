"""
src/backup/backup_restore.py

Restore engine. Every call is treated as "cold" — Railway holds no
persistent cache of the backup catalog between requests (see
docs/09_Architecture_Decisions.md ADR-020), so list_backups()/
get_backup_entry()/restore() all start by rebuilding the catalog straight
from R2's own object listing, never trusting a previous in-memory or
on-disk copy. This is a stronger guarantee than a "cold start" fallback —
here, it's how the system always works, not a special-case recovery path.

Restoring means writing the archived files back to GitHub via the Contents
API — GitHub remains the system's one production source of truth
(docs/01_Architecture.md §10, "GitHub is the database"); this module never
writes anything directly into Railway's filesystem or the browser's state.
A restore is an ordinary, auditable git commit, identified by message as a
restore and naming the source backup id.
"""
from __future__ import annotations

from src.backup import backup_index
from src.backup.backup_validator import extract_files, validate_archive
from src.backup.r2_client import R2ObjectNotFoundError


class RestoreError(RuntimeError):
    pass


def _created_at_from_id(backup_id: str) -> str | None:
    # id shape: <YYYY-MM-DDTHH-mm-ss-fff>-<type>-<hex8>
    try:
        date_part, rest = backup_id.split("T", 1)
        time_fields = rest.split("-")[:4]  # HH mm ss fff
        return f"{date_part}T{time_fields[0]}:{time_fields[1]}:{time_fields[2]}.{time_fields[3]}+00:00"
    except Exception:
        return None


def rebuild_index_from_r2(r2_client) -> dict:
    """Lists every object under backups/ and returns a lightweight catalog
    built entirely from that listing (no per-object download) — cheap
    enough to run on every single call (status, list, restore), which is
    exactly what this design requires given Railway has nowhere durable to
    cache the result between requests."""
    objects = r2_client.list_objects("backups/")
    backups = []
    for obj in objects:
        if obj.key == backup_index.INDEX_KEY:
            continue
        parts = obj.key.split("/")  # backups/<type>/<id>.zip
        if len(parts) != 3 or not parts[2].endswith(".zip"):
            continue
        backup_type = parts[1]
        backup_id = parts[2][: -len(".zip")]
        backups.append({
            "id": backup_id,
            "type": backup_type,
            "key": obj.key,
            "sizeBytes": obj.size,
            "createdAt": _created_at_from_id(backup_id),
        })
    return {"updatedAt": None, "backups": backups, "source": "r2_listing"}


def list_backups(r2_client) -> list[dict]:
    index = rebuild_index_from_r2(r2_client)
    return sorted(index["backups"], key=lambda b: b.get("createdAt") or "", reverse=True)


def get_backup_entry(r2_client, backup_id: str) -> dict | None:
    for b in list_backups(r2_client):
        if b["id"] == backup_id:
            return b
    return None


def get_recovery_status(r2_client) -> dict:
    """Summary used by the dashboard's Backups view and GET /backup/status —
    is there anything to restore from, and how fresh is it."""
    backups = list_backups(r2_client)
    if not backups:
        return {"recoverable": False, "issues": ["no backups found in R2"], "latest": None, "count": 0}
    latest = backups[0]
    return {"recoverable": True, "issues": [], "latest": latest, "count": len(backups)}


def _download_and_validate(r2_client, entry: dict) -> tuple[bytes, dict]:
    try:
        zip_bytes = r2_client.get_object(entry["key"])
    except R2ObjectNotFoundError as e:
        raise RestoreError(
            f"backup {entry['id']} is indexed but its R2 object is missing: {entry['key']}"
        ) from e
    validation = validate_archive(zip_bytes)
    return zip_bytes, validation


def _validate_restore_with_bytes(r2_client, backup_id: str) -> tuple[dict, bytes | None]:
    """The single implementation behind both validate_restore() (public
    dry-run, never exposes the downloaded bytes to its caller) and
    restore() (which needs the actual bytes it already validated, not a
    second download of them).

    Phase 27.3 fix (identified by the Phase 27.2A resource audit): restore()
    used to call validate_restore() for its pre-check and then download the
    archive a *second* time to actually extract it — one R2 GET wasted on
    every single restore, doubling network time/egress cost at any archive
    size. This helper downloads exactly once; both public functions below
    share that one download.
    """
    entry = get_backup_entry(r2_client, backup_id)
    if entry is None:
        return {"ok": False, "id": backup_id, "reason": "BACKUP_NOT_FOUND", "entry": None, "validation": None}, None
    zip_bytes, validation = _download_and_validate(r2_client, entry)
    ok = validation["status"] != "corrupted"
    preview = {
        "ok": ok,
        "id": backup_id,
        "entry": entry,
        "validation": validation,
        "reason": None if ok else "BACKUP_CORRUPTED",
    }
    return preview, zip_bytes


def validate_restore(r2_client, backup_id: str) -> dict:
    """Dry-run: download + validate, change nothing. Used by both the
    dashboard's preview step and internally by restore() (via
    _validate_restore_with_bytes(), not this function directly — see its
    docstring), so the two can never disagree about whether a given backup
    is restorable (mirrors the basketball-over-bot precedent's
    restoreEngine._resolveArchive() design). Deliberately never returns the
    downloaded bytes — this is the public, HTTP-facing shape
    (POST /backup/validate-restore's response), and raw archive bytes have
    no business being serialized into a JSON API response."""
    preview, _zip_bytes = _validate_restore_with_bytes(r2_client, backup_id)
    return preview


def restore(r2_client, backup_id: str, *, confirmed: bool, write_file_fn,
            pre_restore_snapshot_fn=None) -> dict:
    """Executes a restore.

    `write_file_fn(path, content_text, message)` is injected rather than
    imported directly, so this module stays fully testable without any real
    GitHub credentials — the production caller (sync_server.py) passes
    github_files.write_file.

    `pre_restore_snapshot_fn()` — if provided, called before any GitHub
    write; the whole restore aborts if it raises, mirroring the
    basketball-over-bot precedent's mandatory pre-restore safety snapshot
    (a restore is always itself one more restore away from being undone).

    Downloads the target archive exactly once (Phase 27.3 fix — see
    _validate_restore_with_bytes()'s docstring) — integrity verification,
    restore validation, and the actual extraction all operate on that same
    single download, with no change to any of their individual checks.
    """
    if not confirmed:
        raise RestoreError("restore requires confirmed=True — call validate_restore() first")

    preview, zip_bytes = _validate_restore_with_bytes(r2_client, backup_id)
    if not preview["ok"]:
        raise RestoreError(f"cannot restore backup {backup_id}: {preview['reason']}")

    if pre_restore_snapshot_fn is not None:
        try:
            pre_restore_snapshot_fn()
        except Exception as e:
            raise RestoreError(
                f"pre-restore safety snapshot failed — restore aborted, nothing written: {e}"
            ) from e

    files = extract_files(zip_bytes)

    written, failed = [], []
    for name, content in files.items():
        if name == "extra_payload.json":
            continue  # not a GitHub-tracked file — restored data only, never written back to GitHub
        try:
            write_file_fn(name, content.decode("utf-8"), f"restore: {name} from backup {backup_id}")
            written.append(name)
        except Exception as e:
            failed.append({"name": name, "error": str(e)})

    return {
        "id": backup_id,
        "written": written,
        "failed": failed,
        "success": len(failed) == 0,
        "sourceKey": preview["entry"]["key"],
    }
