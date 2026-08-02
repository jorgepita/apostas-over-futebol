import base64
import json
import os
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "jorgepita").strip()
GITHUB_REPO  = os.environ.get("GITHUB_REPO",  "apostas-over-futebol").strip()
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main").strip()

if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN em falta")

SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "apostas-dashboard-sync",
})

CLOUD_STATE_PATH = "cloud_state.json"


def github_contents_url(path: str) -> str:
    return f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def github_request(method: str, url: str, **kwargs):
    return SESSION.request(method, url, timeout=15, **kwargs)


def get_file_from_github(path: str):
    try:
        url  = github_contents_url(path)
        resp = github_request("GET", url, params={"ref": GITHUB_BRANCH})

        if resp.status_code == 404:
            return None, None

        resp.raise_for_status()
        data        = resp.json()
        content_b64 = data.get("content", "") or ""
        sha         = data.get("sha")

        if not content_b64:
            return "", sha

        decoded = base64.b64decode(content_b64).decode("utf-8")
        return decoded, sha

    except Exception as e:
        print(f"GitHub read error ({path}): {e}", flush=True)
        return None, None


def _manual_bet_identity(bet: dict):
    """Same-opportunity identity for a manual bet: fixture + market.

    Reuses the exact normalisation the settlement engine already applies
    (_resolve_liga_display_name / _normalize_market_code) instead of a second,
    independent implementation — see ADR-004/ADR-009 on avoiding parallel
    business logic for the same concept.
    """
    from update_results import _resolve_liga_display_name, _normalize_market_code

    data = str(bet.get("data") or "").strip()
    liga_raw = str(bet.get("liga") or "").strip()
    liga = _resolve_liga_display_name(liga_raw).strip().lower() if liga_raw else ""
    jogo = str(bet.get("jogo") or "").strip().lower()
    mercado = _normalize_market_code(bet.get("mercado") or "")
    return (data, liga, jogo, mercado)


def _dedupe_manual_bets(manual_bets):
    """Guard against two manual bets for the same fixture+market reaching
    cloud_state.json — double-clicks, a race between two browser tabs, or a
    stale local copy re-submitting a bet the cloud already has. The frontend
    already hides/blocks this in normal use; this is the authoritative,
    server-side backstop (see ADR-013).

    Keeps the earliest occurrence per identity (the array is append-ordered,
    so the first occurrence is the original bet); later duplicates are
    dropped. Bets that fail to resolve an identity (missing fields) are kept
    as-is rather than risk dropping a legitimate record.
    """
    if not isinstance(manual_bets, list):
        return manual_bets, 0

    seen = set()
    deduped = []
    dropped = 0
    for bet in manual_bets:
        if not isinstance(bet, dict):
            deduped.append(bet)
            continue
        try:
            identity = _manual_bet_identity(bet)
        except Exception:
            deduped.append(bet)
            continue
        if not all(identity):
            deduped.append(bet)
            continue
        if identity in seen:
            dropped += 1
            print(
                f"[save] dropped duplicate manual bet: {bet.get('jogo')} | "
                f"{bet.get('mercado')} | id={bet.get('id')}",
                flush=True,
            )
            continue
        seen.add(identity)
        deduped.append(bet)
    return deduped, dropped


def put_file_to_github(path: str, content_text: str, message: str, sha=None):
    url     = github_contents_url(path)
    payload = {
        "message": message,
        "content": base64.b64encode(content_text.encode("utf-8")).decode("utf-8"),
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    resp = github_request("PUT", url, json=payload)
    resp.raise_for_status()
    return resp.json()


@app.get("/")
def root():
    return jsonify({
        "ok":       True,
        "service":  "apostas-dashboard-sync",
        "endpoints": [
            "/health", "/load", "/save", "/run-settlement",
            "/backup/status", "/backup/create", "/backup/validate-restore", "/backup/restore",
        ],
        "repo":     f"{GITHUB_OWNER}/{GITHUB_REPO}",
        "branch":   GITHUB_BRANCH,
    })


@app.get("/health")
def health():
    return jsonify({
        "ok":      True,
        "service": "apostas-dashboard-sync",
        "time":    utc_now_iso(),
    })


@app.get("/load")
def load_cloud_state():
    try:
        content_text, _sha = get_file_from_github(CLOUD_STATE_PATH)
        if content_text is None:
            return jsonify({})
        parsed = json.loads(content_text) if content_text.strip() else {}
        return jsonify(parsed)
    except Exception as e:
        print("GET /load error:", e, flush=True)
        return jsonify({"error": str(e)}), 500


@app.post("/save")
def save_cloud_state():
    try:
        payload = request.get_json(force=True, silent=False)
        content = payload.get("content")
        message = payload.get("message", "update cloud state")
        if content is None:
            return jsonify({"error": "Missing content"}), 400

        duplicates_removed = 0
        if isinstance(content, dict) and isinstance(content.get("manualBets"), list):
            deduped_bets, duplicates_removed = _dedupe_manual_bets(content["manualBets"])
            if duplicates_removed:
                content = {**content, "manualBets": deduped_bets}

        content_text = json.dumps(content, indent=2)
        _old, sha    = get_file_from_github(CLOUD_STATE_PATH)
        result       = put_file_to_github(CLOUD_STATE_PATH, content_text, message, sha=sha)
        new_sha      = result.get("content", {}).get("sha")
        response = {"success": True, "sha": new_sha}
        if duplicates_removed:
            response["duplicatesRemoved"] = duplicates_removed
        return jsonify(response)
    except Exception as e:
        print("POST /save error:", e, flush=True)
        return jsonify({"error": str(e)}), 500


@app.post("/run-settlement")
def run_settlement():
    try:
        from update_results import run_settlement_remote
        result = run_settlement_remote()
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("POST /run-settlement error:", e, flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================================
# Backup & Disaster Recovery (Phase 27.2, production-hardened Phase 27.3) —
# see docs/09_Architecture_Decisions.md ADR-020 and its Phase 27.3
# "Production Hardening" addendum. Every handler below fetches R2
# credentials fresh per-request and holds nothing on Railway's disk at any
# point — matching this file's existing "the Railway server holds no state
# between requests" rule (see docs/01_Architecture.md §2/§10). 'scheduled'
# backups are created only by the GitHub Actions cron job (backup_job.py),
# never through this endpoint — see /backup/create's type validation below.
#
# Response shape convention across all four endpoints: every error response
# is `{"error": "<message>"}` with a status code reflecting the failure's
# nature — 400 for a bad/missing request parameter or an unrestorable
# backup (client-correctable), 503 for R2 being unreachable/misconfigured
# (retry later / an operator needs to act, not the caller), 500 for
# anything else unexpected. No error message ever includes a credential
# value — see r2_client.py's error-classification docstring and this
# phase's security audit.
# =============================================================================

def _r2_client_or_error_response():
    """Shared by every action endpoint (create/validate-restore/restore) —
    one implementation of "how to fail when R2 isn't reachable or
    configured," so all three respond identically instead of three
    hand-copied try/except blocks that could drift apart. `GET
    /backup/status` deliberately does NOT use this helper — a status check
    reporting "not configured" is itself a successful (200) response, not
    an error, a different semantic than the action endpoints below.

    Returns (client, None) on success, or (None, (response, status)) on
    failure — callers do:
        r2_client, err = _r2_client_or_error_response()
        if err:
            return err
    """
    from src.backup.config import get_r2_settings
    from src.backup.r2_client import R2NotConfiguredError, get_r2_client
    try:
        return get_r2_client(get_r2_settings()), None
    except R2NotConfiguredError as e:
        return None, (jsonify({"error": f"R2 not configured: {e}"}), 503)
    except Exception as e:
        # R2Client construction can itself fail (e.g. a malformed region or
        # endpoint reaching botocore's own validation) — never let that
        # escape as an unhandled 500 with no explanation.
        print("R2 client construction error:", e, flush=True)
        return None, (jsonify({"error": f"R2 client could not be constructed: {e}"}), 503)


@app.get("/backup/status")
def backup_status():
    from src.backup.backup_restore import get_recovery_status, list_backups
    from src.backup.config import get_r2_settings
    from src.backup.r2_client import R2NotConfiguredError, get_r2_client

    try:
        r2_client = get_r2_client(get_r2_settings())
    except R2NotConfiguredError as e:
        return jsonify({"r2Configured": False, "reason": str(e), "backups": [], "recovery": None})
    except Exception as e:
        print("GET /backup/status R2 client error:", e, flush=True)
        return jsonify({"r2Configured": False, "reason": str(e), "backups": [], "recovery": None})

    try:
        backups = list_backups(r2_client)
        recovery = get_recovery_status(r2_client)
    except Exception as e:
        print("GET /backup/status error:", e, flush=True)
        return jsonify({"error": str(e)}), 500

    integrity = None
    if request.args.get("verify") == "1":
        from src.backup.backup_integrity import verify_remote_integrity
        try:
            integrity = verify_remote_integrity(r2_client)
        except Exception as e:
            integrity = {"error": str(e)}

    return jsonify({"r2Configured": True, "backups": backups, "recovery": recovery, "integrity": integrity})


@app.post("/backup/create")
def backup_create():
    from src.backup import github_files
    from src.backup.backup_engine import BackupError, create_backup
    from src.backup.config import get_backup_config

    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        payload = {}

    backup_type = payload.get("type", "manual")
    if backup_type not in ("manual", "critical"):
        return jsonify({
            "error": "type must be 'manual' or 'critical' — 'scheduled' backups are "
                     "created only by the GitHub Actions cron job, not this endpoint",
        }), 400

    reason = payload.get("reason")
    extra_payload = payload.get("extraPayload")

    r2_client, err = _r2_client_or_error_response()
    if err:
        return err

    cfg = get_backup_config()
    try:
        files = github_files.fetch_files(cfg["files"])
        github_commit_sha = github_files.fetch_commit_sha(CLOUD_STATE_PATH)
    except Exception as e:
        print("POST /backup/create GitHub fetch error:", e, flush=True)
        return jsonify({"error": f"failed to fetch files from GitHub: {e}"}), 500

    if not files:
        return jsonify({"error": "no production files found on GitHub — nothing to back up"}), 500

    try:
        result = create_backup(
            backup_type, files=files, r2_client=r2_client, reason=reason,
            github_commit_sha=github_commit_sha, extra_payload=extra_payload,
            retention_cfg=cfg["retention"],
        )
    except BackupError as e:
        print("POST /backup/create error:", e, flush=True)
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        print("POST /backup/create unexpected error:", e, flush=True)
        return jsonify({"error": f"unexpected error creating backup: {e}"}), 500

    return jsonify({"success": True, "backup": result})


@app.post("/backup/validate-restore")
def backup_validate_restore():
    from src.backup.backup_restore import validate_restore

    payload = request.get_json(force=True, silent=True) or {}
    backup_id = payload.get("id")
    if not backup_id:
        return jsonify({"error": "Missing id"}), 400

    r2_client, err = _r2_client_or_error_response()
    if err:
        return err

    try:
        return jsonify(validate_restore(r2_client, backup_id))
    except Exception as e:
        print("POST /backup/validate-restore error:", e, flush=True)
        return jsonify({"error": str(e)}), 500


@app.post("/backup/restore")
def backup_restore_endpoint():
    from src.backup import github_files
    from src.backup.backup_engine import create_backup
    from src.backup.backup_restore import RestoreError, restore
    from src.backup.config import get_backup_config

    payload = request.get_json(force=True, silent=True) or {}
    backup_id = payload.get("id")
    confirmed = payload.get("confirmed") is True
    if not backup_id:
        return jsonify({"error": "Missing id"}), 400

    r2_client, err = _r2_client_or_error_response()
    if err:
        return err

    cfg = get_backup_config()

    def _pre_restore_snapshot():
        # Mandatory — a restore is always itself one more restore away from
        # being undone. Aborts the whole restore (nothing written to
        # GitHub) if this snapshot itself fails. See ADR-020.
        snapshot_files = github_files.fetch_files(cfg["files"])
        create_backup(
            "critical", files=snapshot_files, r2_client=r2_client,
            reason="pre_restore_safety", retention_cfg=cfg["retention"],
        )

    try:
        result = restore(
            r2_client, backup_id, confirmed=confirmed,
            write_file_fn=github_files.write_file,
            pre_restore_snapshot_fn=_pre_restore_snapshot,
        )
    except RestoreError as e:
        print("POST /backup/restore error:", e, flush=True)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print("POST /backup/restore unexpected error:", e, flush=True)
        return jsonify({"error": f"unexpected error during restore: {e}"}), 500

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)
