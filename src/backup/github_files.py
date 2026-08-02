"""
src/backup/github_files.py

Thin adapter over update_results.py's existing GitHub Contents API
primitives (github_request / github_get_sha / github_put_file /
github_get_file_bytes) — reused rather than reimplemented, per this
project's rule that persistence logic must have exactly one implementation
(docs/01_Architecture.md §10, "GitHub is the database"). This module adds
no new way of talking to GitHub; it only adapts those existing functions to
the shape the backup engine needs.

`update_results` is imported lazily, inside each function rather than at
module load time — matching sync_server.py's own existing convention
(`from update_results import run_settlement_remote` inside the
`/run-settlement` handler, not at the top of the file) so that importing
this module never pulls in pandas or any other heavy dependency unless a
GitHub-backed backup operation is actually invoked.

Used by:
- Railway (sync_server.py's backup endpoints) to fetch the current
  cloud_state.json/CSVs fresh before building a manual/critical backup, and
  to write restored files back to GitHub during a restore.
- NOT used by the scheduled GitHub Actions backup job — that job already
  has every file on disk via actions/checkout, so no GitHub API read is
  needed there at all (see backup_job.py).
"""
from __future__ import annotations

import os
from urllib import error


def _github_identity():
    import update_results as ur
    owner = os.getenv("GITHUB_OWNER", "").strip() or ur.GITHUB_OWNER
    repo = os.getenv("GITHUB_REPO", "").strip() or ur.GITHUB_REPO
    branch = os.getenv("GITHUB_BRANCH", "").strip() or ur.GITHUB_BRANCH
    token = os.getenv("GITHUB_TOKEN", "").strip()
    return ur, owner, repo, branch, token


def fetch_file(path: str) -> str | None:
    """Returns file content as text, or None if it doesn't exist on GitHub (404)."""
    ur, owner, repo, branch, token = _github_identity()
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set — cannot fetch files from GitHub")
    try:
        raw = ur.github_get_file_bytes(owner, repo, path, branch, token)
        return raw.decode("utf-8")
    except error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def fetch_commit_sha(path: str) -> str | None:
    ur, owner, repo, branch, token = _github_identity()
    if not token:
        return None
    return ur.github_get_sha(owner, repo, path, branch, token)


def write_file(path: str, content_text: str, message: str) -> None:
    ur, owner, repo, branch, token = _github_identity()
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set — cannot write files to GitHub")
    ur.github_put_file(owner, repo, path, content_text.encode("utf-8"), branch, token, message)


def fetch_files(paths: list[str]) -> dict[str, bytes]:
    """Fetches every path that exists on GitHub; silently omits any that
    return 404 (e.g. sent_state.json may legitimately not exist yet) —
    mirrors backup_job.py's identical tolerance for a missing local file."""
    out: dict[str, bytes] = {}
    for path in paths:
        text = fetch_file(path)
        if text is not None:
            out[path] = text.encode("utf-8")
    return out
