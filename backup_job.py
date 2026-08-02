"""
backup_job.py

Entry point for the scheduled GitHub Actions backup job (Phase 27.2). Run
by .github/workflows/bot.yml's `backup` job, every 6 hours (UTC).

Reads the already-checked-out production files directly from disk — the
GitHub Actions runner has them via actions/checkout, so no GitHub API read
is needed for backup CREATION here, unlike Railway's on-demand backup
endpoints, which have no local checkout at all and fetch fresh via the
Contents API (see src/backup/github_files.py). Builds one 'scheduled'
backup and uploads it to Cloudflare R2. See docs/09_Architecture_Decisions.md
ADR-020 and docs/04_Backend.md for the full design.

If R2 is not configured (R2_ENABLED unset, or credentials missing), this
prints a warning and exits 0 — a missing backup configuration must never
fail the wider bot.yml workflow run, mirroring how this project already
treats settlement/league-stats persistence failures as log-and-skip, never
fatal (docs/01_Architecture.md §10, "Settlement skips rather than fails").
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from src.backup.backup_engine import BackupError, create_backup  # noqa: E402
from src.backup.config import get_backup_config, get_r2_settings  # noqa: E402
from src.backup.r2_client import R2NotConfiguredError, get_r2_client  # noqa: E402


def _read_local_files(filenames: list[str]) -> dict[str, bytes]:
    files = {}
    for name in filenames:
        path = BASE / name
        if path.exists():
            files[name] = path.read_bytes()
        else:
            print(f"[backup_job] skipping missing file: {name}")
    return files


def main() -> int:
    cfg = get_backup_config()
    if not cfg["enabled"]:
        print("[backup_job] backups disabled in config.json — nothing to do")
        return 0

    try:
        r2_client = get_r2_client(get_r2_settings())
    except R2NotConfiguredError as e:
        print(f"[backup_job] R2 not configured, skipping scheduled backup: {e}")
        return 0

    files = _read_local_files(cfg["files"])
    if not files:
        print("[backup_job] no production files found on disk — nothing to back up")
        return 0

    try:
        result = create_backup("scheduled", files=files, r2_client=r2_client,
                                retention_cfg=cfg["retention"])
    except BackupError as e:
        print(f"[backup_job] ERROR: backup creation failed: {e}")
        return 1

    print(f"[backup_job] backup created: {result['id']} "
          f"({result['fileCount']} files, {result['sizeBytes']} bytes)")
    evicted = result.get("retention", {}).get("evicted")
    if evicted:
        print(f"[backup_job] retention evicted: {[e['id'] for e in evicted]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
