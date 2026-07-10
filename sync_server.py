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
        "endpoints": ["/health", "/load", "/save", "/run-settlement"],
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)
