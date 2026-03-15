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
    "User-Agent": "apostas-dashboard-sync"
}


def github_contents_url(path: str) -> str:
    return f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"


def get_file_from_github(path: str):
    url = github_contents_url(path)
    resp = requests.get(url, headers=HEADERS, params={"ref": GITHUB_BRANCH})

    if resp.status_code == 404:
        return None, None

    resp.raise_for_status()
    data = resp.json()
    content_b64 = data.get("content", "")
    sha = data.get("sha")
    decoded = base64.b64decode(content_b64).decode("utf-8")
    return decoded, sha


def put_file_to_github(path: str, content_text: str, message: str, sha=None):
    url = github_contents_url(path)
    payload = {
        "message": message,
        "content": base64.b64encode(content_text.encode("utf-8")).decode("utf-8"),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(url, headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.get("/state")
def get_state():
    content, _sha = get_file_from_github(STATE_PATH)

    if content is None:
        return jsonify({
            "ok": True,
            "state": {
                "bankrollInicial": 1000,
                "localEdits": {},
                "manualBets": []
            }
        })

    return jsonify({"ok": True, "state": json.loads(content)})


@app.post("/state")
def save_state():
    payload = request.get_json()

    state = {
        "bankrollInicial": payload.get("bankrollInicial", 1000),
        "localEdits": payload.get("localEdits", {}),
        "manualBets": payload.get("manualBets", []),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }

    old_content, sha = get_file_from_github(STATE_PATH)

    put_file_to_github(
        STATE_PATH,
        json.dumps(state, indent=2),
        "update dashboard state",
        sha=sha
    )

    return jsonify({"ok": True})
