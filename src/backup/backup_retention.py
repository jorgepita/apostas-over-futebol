"""
src/backup/backup_retention.py

Index-based retention (never a bucket-listing scan for the eviction
decision itself — only backup_restore.rebuild_index_from_r2() ever trusts a
raw listing, and only to rebuild the catalog, never to decide what to
keep). Every backup type has its own independent policy:

- scheduled: keep the newest `scheduled_max_count` entries (default 60 —
  roughly 15 days of coverage at the 6-hourly GitHub Actions cadence the
  Phase 27.1 report recommended).
- manual: keep entries newer than `manual_max_age_days` (default 90).
- critical: no cap by default (`critical_max_count: None`) — these mark a
  specific, named, high-stakes moment (e.g. immediately before an
  End-of-Season close) and, at well under 1 MB per archive, the storage
  cost of keeping all of them indefinitely is negligible. Set a real
  number in config.json["backup"]["retention"]["critical_max_count"] if
  that assumption ever needs to change.

Eviction order within a capped type: oldest first. Removal is always
R2-object-then-index-entry (never the reverse) — a failed R2 delete leaves
the index entry in place rather than orphaning the object with nothing
left pointing at it (see docs/09_Architecture_Decisions.md ADR-020).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.backup import backup_index
from src.backup.r2_client import R2ObjectNotFoundError


def _evict(r2_client, backup_id: str, key: str) -> dict:
    try:
        r2_client.delete_object(key)
    except R2ObjectNotFoundError:
        pass  # already gone — fine, proceed to drop the index entry too
    except Exception as e:
        return {"id": backup_id, "evicted": False, "error": str(e)}
    backup_index.remove_entry(r2_client, backup_id)
    return {"id": backup_id, "evicted": True}


def run_retention(r2_client, retention_cfg: dict) -> dict:
    index = backup_index.read_index(r2_client)
    backups = index.get("backups", [])
    results = []

    # ── scheduled: count cap ────────────────────────────────────────────
    scheduled = sorted(
        (b for b in backups if b.get("type") == "scheduled"),
        key=lambda b: b.get("createdAt", ""),
    )
    max_scheduled = retention_cfg.get("scheduled_max_count")
    if isinstance(max_scheduled, int) and max_scheduled > 0 and len(scheduled) > max_scheduled:
        for b in scheduled[: len(scheduled) - max_scheduled]:
            results.append(_evict(r2_client, b["id"], b["key"]))

    # ── manual: age cap ──────────────────────────────────────────────────
    max_age_days = retention_cfg.get("manual_max_age_days")
    if isinstance(max_age_days, (int, float)) and max_age_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        for b in backups:
            if b.get("type") != "manual":
                continue
            try:
                created = datetime.fromisoformat(b.get("createdAt", ""))
            except (ValueError, TypeError):
                continue
            if created < cutoff:
                results.append(_evict(r2_client, b["id"], b["key"]))

    # ── critical: optional count cap (default: unlimited) ───────────────
    max_critical = retention_cfg.get("critical_max_count")
    if isinstance(max_critical, int) and max_critical > 0:
        critical = sorted(
            (b for b in backups if b.get("type") == "critical"),
            key=lambda b: b.get("createdAt", ""),
        )
        if len(critical) > max_critical:
            for b in critical[: len(critical) - max_critical]:
                results.append(_evict(r2_client, b["id"], b["key"]))

    return {
        "evicted": [r for r in results if r.get("evicted")],
        "failed": [r for r in results if not r.get("evicted")],
    }
