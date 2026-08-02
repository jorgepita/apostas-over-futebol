"""
src/backup/backup_integrity.py

Proactive R2 drift detection — HEAD-only, never downloads. Confirms every
object the *persisted index* (backups/index.json) claims exists actually
still does.

Deliberately reads backup_index.read_index() here, NOT
backup_restore.list_backups()/rebuild_index_from_r2() — those are built
directly from a fresh R2 listing, so by construction they can never show an
externally-deleted object as "missing" (a deleted object simply doesn't
appear in the listing at all, which looks identical to "never existed").
Only the index's own recorded claims can be checked against reality; that
is the entire point of this module. An out-of-band deletion (an operator in
the R2 dashboard, a misconfigured lifecycle policy, external tooling) is
otherwise only ever discovered reactively, at actual restore time. See
docs/09_Architecture_Decisions.md ADR-020.
"""
from __future__ import annotations

from src.backup import backup_index
from src.backup.r2_client import R2ObjectNotFoundError


def verify_remote_integrity(r2_client) -> dict:
    backups = backup_index.read_index(r2_client).get("backups", [])
    healthy, missing, errors = [], [], []
    for b in backups:
        try:
            info = r2_client.head_object(b["key"])
            if info.size != b.get("sizeBytes"):
                missing.append({**b, "checkReason": "size_mismatch", "actualSize": info.size})
            else:
                healthy.append(b["id"])
        except R2ObjectNotFoundError:
            missing.append({**b, "checkReason": "not_found"})
        except Exception as e:
            errors.append({**b, "checkError": str(e)})

    return {
        "totalChecked": len(backups),
        "healthyCount": len(healthy),
        "missing": missing,
        "errors": errors,
    }
