"""
backup_integrity_job.py

Entry point for the weekly GitHub Actions R2 integrity sweep (Phase 27.2).
Run by .github/workflows/bot.yml's `backup-integrity` job (Sunday 04:00
UTC). HEAD-only — never downloads an archive — confirms every backup the
freshly-rebuilt catalog believes exists in R2 actually still does. See
src/backup/backup_integrity.py and docs/09_Architecture_Decisions.md
ADR-020.

Same non-fatal-if-unconfigured behaviour as backup_job.py: a missing R2
configuration prints a warning and exits 0 rather than failing the
workflow. A confirmed-missing backup object DOES exit non-zero (1), so the
GitHub Actions run shows as failed and is visible without anyone having to
read logs proactively — the only case in this script that should actually
draw attention.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from src.backup.backup_integrity import verify_remote_integrity  # noqa: E402
from src.backup.config import get_r2_settings  # noqa: E402
from src.backup.r2_client import R2NotConfiguredError, get_r2_client  # noqa: E402


def main() -> int:
    try:
        r2_client = get_r2_client(get_r2_settings())
    except R2NotConfiguredError as e:
        print(f"[backup_integrity_job] R2 not configured, skipping integrity sweep: {e}")
        return 0

    report = verify_remote_integrity(r2_client)
    print(f"[backup_integrity_job] checked {report['totalChecked']} backups: "
          f"{report['healthyCount']} healthy, {len(report['missing'])} missing, "
          f"{len(report['errors'])} check errors")

    if report["missing"]:
        for m in report["missing"]:
            print(f"[backup_integrity_job] MISSING: {m['id']} ({m['key']}) — {m['checkReason']}")
        return 1

    if report["errors"]:
        for e in report["errors"]:
            print(f"[backup_integrity_job] WARNING: check error for {e['id']}: {e['checkError']}")
        # A transient check error is a warning, not a confirmed loss — never
        # fails the workflow on its own (see backup_integrity.py's
        # docstring on distinguishing a 404 from a network blip).

    return 0


if __name__ == "__main__":
    sys.exit(main())
