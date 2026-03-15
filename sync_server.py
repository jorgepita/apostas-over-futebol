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
GITHUB_REPO = os.environ.get("GITHUB_REPO", "apostas-over-futebol").strip()
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main").strip()
STATE_PATH = os.environ.get("STATE_PATH", "dashboard_state.json").strip()

if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN em falta")

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "apostas-dashboard-sync",
}


def github_contents_url(path: str) -> str:
    return f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"


def get_file_from_github(path: str):
    try:
        url = github_contents_url(path)
        resp = requests.get(
            url,
            headers=HEADERS,
            params={"ref": GITHUB_BRANCH},
            timeout=10,
        )

        if resp.status_code == 404:
            return None, None

        resp.raise_for_status()
        data = resp.json()
        content_b64 = data.get("content", "")
        sha = data.get("sha")

        if not content_b64:
            return None, sha

        decoded = base64.b64decode(content_b64).decode("utf-8")
        return decoded, sha

    except Exception as e:
        print("GitHub read error:", e, flush=True)
        return None, None


def put_file_to_github(path: str, content_text: str, message: str, sha=None):
    url = github_contents_url(path)
    payload = {
        "message": message,
        "content": base64.b64encode(content_text.encode("utf-8")).decode("utf-8"),
        "branch": GITHUB_BRANCH,
    }

    if sha:
        payload["sha"] = sha

    resp = requests.put(
        url,
        headers=HEADERS,
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def validate_state(payload):
    if not isinstance(payload, dict):
        raise ValueError("Payload inválido")

    bankroll = payload.get("bankrollInicial", 1000)
    local_edits = payload.get("localEdits", {})
    manual_bets = payload.get("manualBets", [])

    if not isinstance(local_edits, dict):
        raise ValueError("localEdits tem de ser objeto")

    if not isinstance(manual_bets, list):
        raise ValueError("manualBets tem de ser lista")

    return {
        "bankrollInicial": bankroll,
        "localEdits": local_edits,
        "manualBets": manual_bets,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
def root():
    return jsonify({
        "ok": True,
        "service": "apostas-dashboard-sync",
        "endpoints": ["/health", "/state"],
    })


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.get("/state")
def get_state():
    try:
        content, _sha = get_file_from_github(STATE_PATH)

        if content is None:
            return jsonify({
                "ok": True,
                "exists": False,
                "state": {
                    "bankrollInicial": 1000,
                    "localEdits": {},
                    "manualBets": [],
                    "updatedAt": None,
                },
            })

        parsed = json.loads(content)
        return jsonify({
            "ok": True,
            "exists": True,
            "state": parsed,
        })

    except Exception as e:
        print("GET /state error:", e, flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/state")
def save_state():
    try:
        payload = request.get_json(force=True, silent=False)
        state = validate_state(payload)

        _old_content, sha = get_file_from_github(STATE_PATH)

        put_file_to_github(
            STATE_PATH,
            json.dumps(state, ensure_ascii=False, indent=2),
            "update dashboard state",
            sha=sha,
        )

        return jsonify({"ok": True, "state": state})

    except Exception as e:
        print("POST /state error:", e, flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)
