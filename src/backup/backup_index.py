"""
src/backup/backup_index.py

The backup catalog. Lives in R2 itself (backups/index.json) — never cached
on Railway between requests, since Railway holds no persistent state at all
(see docs/09_Architecture_Decisions.md ADR-020, and docs/01_Architecture.md
§2's existing "Railway holds no state between requests" rule, which this
module deliberately preserves rather than quietly working around). Every
read is a fresh R2 GET; every write is a fresh R2 PUT of the whole (small)
index object.

Known limitation (documented, not solved here — see ADR-020 Consequences):
this is a read-modify-write pattern, not a compare-and-swap. Two backup
operations landing at almost the exact same instant could race and one
entry could be dropped from the index — the R2 object itself would still
exist, just uncatalogued until the next backup_restore.rebuild_index_from_r2()
call, which is index-agnostic and always finds every real object regardless
of what the index believes. Acceptable given this project's actual write
cadence (a handful of backups a day, from callers that are essentially
never both mid-request at once in practice) — flagged here for whoever
revisits this if that assumption ever stops holding.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.backup.r2_client import R2ObjectNotFoundError

INDEX_KEY = "backups/index.json"


def read_index(r2_client) -> dict:
    try:
        raw = r2_client.get_object(INDEX_KEY)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict) or not isinstance(parsed.get("backups"), list):
            return {"updatedAt": None, "backups": []}
        return parsed
    except R2ObjectNotFoundError:
        return {"updatedAt": None, "backups": []}
    except (json.JSONDecodeError, UnicodeDecodeError):
        # A corrupted index is never trusted silently — treat as empty
        # rather than raising, so the caller (e.g. a scheduled backup job)
        # doesn't crash over a catalog problem alone; backup_restore.py's
        # rebuild_index_from_r2() remains the ground truth regardless.
        return {"updatedAt": None, "backups": []}


def write_index(r2_client, index: dict) -> None:
    index = dict(index)
    index["updatedAt"] = datetime.now(timezone.utc).isoformat()
    r2_client.put_object(INDEX_KEY, json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8"))


def add_entry(r2_client, entry: dict) -> dict:
    index = read_index(r2_client)
    index["backups"] = [b for b in index["backups"] if b.get("id") != entry.get("id")]
    index["backups"].append(entry)
    write_index(r2_client, index)
    return index


def remove_entry(r2_client, backup_id: str) -> dict:
    index = read_index(r2_client)
    index["backups"] = [b for b in index["backups"] if b.get("id") != backup_id]
    write_index(r2_client, index)
    return index
