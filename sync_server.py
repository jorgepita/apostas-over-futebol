import base64
import csv
import io
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
MANUAL_BETS_PATH = os.environ.get("MANUAL_BETS_PATH", "manual_bets.csv").strip()

if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN em falta")

SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "apostas-dashboard-sync",
})

DEFAULT_STATE = {
    "bankrollInicial": 1000,
    "localEdits": {},
    "manualBets": [],
    "sessionStartDate": None,
    "updatedAt": None,
}


def github_contents_url(path: str) -> str:
    return f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_str(value) -> str:
    return str(value or "").strip()


def normalize_date(value) -> str:
    raw = normalize_str(value)
    if not raw:
        return ""

    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]

    if len(raw) == 10 and raw[2] in "/-" and raw[5] in "/-":
        dd = raw[0:2]
        mm = raw[3:5]
        yyyy = raw[6:10]
        if yyyy.isdigit() and mm.isdigit() and dd.isdigit():
            return f"{yyyy}-{mm}-{dd}"

    return ""


def github_request(method: str, url: str, **kwargs):
    response = SESSION.request(method, url, timeout=15, **kwargs)
    return response


def get_file_from_github(path: str):
    try:
        url = github_contents_url(path)
        resp = github_request("GET", url, params={"ref": GITHUB_BRANCH})

        if resp.status_code == 404:
            return None, None

        resp.raise_for_status()
        data = resp.json()
        content_b64 = data.get("content", "") or ""
        sha = data.get("sha")

        if not content_b64:
            return "", sha

        decoded = base64.b64decode(content_b64).decode("utf-8")
        return decoded, sha

    except Exception as e:
        print(f"GitHub read error ({path}): {e}", flush=True)
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

    resp = github_request("PUT", url, json=payload)
    resp.raise_for_status()
    return resp.json()


def sanitize_local_edits(local_edits):
    if not isinstance(local_edits, dict):
        raise ValueError("localEdits tem de ser objeto")

    clean = {}

    for key, value in local_edits.items():
        if not isinstance(value, dict):
            continue

        clean_key = normalize_str(key)
        if not clean_key:
            continue

        clean[clean_key] = {
            "apostada": bool(value.get("apostada", False)),
            "oddReal": normalize_str(value.get("oddReal", "")),
            "stakeReal": normalize_str(value.get("stakeReal", "")),
            "resultadoManual": normalize_str(value.get("resultadoManual", "")).upper(),
        }

    return clean


def sanitize_manual_bet(item):
    if not isinstance(item, dict):
        raise ValueError("Cada manualBet tem de ser objeto")

    resultado = normalize_str(item.get("resultado", "")).upper()
    if resultado not in {"", "W", "L", "P"}:
        resultado = ""

    return {
        "id": normalize_str(item.get("id", "")),
        "data": normalize_date(item.get("data", "")),
        "liga": normalize_str(item.get("liga", "")),
        "jogo": normalize_str(item.get("jogo", "")),
        "mercado": normalize_str(item.get("mercado", "")),
        "odd": normalize_str(item.get("odd", "")),
        "stake": normalize_str(item.get("stake", "")),
        "resultado": resultado,
        "notas": normalize_str(item.get("notas", "")),
    }


def sanitize_manual_bets(manual_bets):
    if not isinstance(manual_bets, list):
        raise ValueError("manualBets tem de ser lista")

    clean = []
    for item in manual_bets:
        sanitized = sanitize_manual_bet(item)
        if sanitized["data"] or sanitized["jogo"] or sanitized["mercado"]:
            clean.append(sanitized)

    return clean


def validate_state(payload):
    if not isinstance(payload, dict):
        raise ValueError("Payload inválido")

    bankroll = payload.get("bankrollInicial", 1000)
    bankroll_num = float(bankroll)
    if bankroll_num < 0:
        bankroll_num = 0.0

    local_edits = sanitize_local_edits(payload.get("localEdits", {}))
    manual_bets = sanitize_manual_bets(payload.get("manualBets", []))
    session_start_date = normalize_date(payload.get("sessionStartDate", ""))

    return {
        "bankrollInicial": round(bankroll_num, 2),
        "localEdits": local_edits,
        "manualBets": manual_bets,
        "sessionStartDate": session_start_date or None,
        "updatedAt": utc_now_iso(),
    }


def normalize_loaded_state(data):
    if not isinstance(data, dict):
        return dict(DEFAULT_STATE)

    bankroll = data.get("bankrollInicial", DEFAULT_STATE["bankrollInicial"])
    try:
        bankroll = round(max(float(bankroll), 0.0), 2)
    except Exception:
        bankroll = DEFAULT_STATE["bankrollInicial"]

    local_edits = {}
    try:
        local_edits = sanitize_local_edits(data.get("localEdits", {}))
    except Exception:
        local_edits = {}

    try:
        manual_bets = sanitize_manual_bets(data.get("manualBets", []))
    except Exception:
        manual_bets = []

    session_start_date = normalize_date(data.get("sessionStartDate", "")) or None
    updated_at = normalize_str(data.get("updatedAt", "")) or None

    return {
        "bankrollInicial": bankroll,
        "localEdits": local_edits,
        "manualBets": manual_bets,
        "sessionStartDate": session_start_date,
        "updatedAt": updated_at,
    }


def manual_bets_to_csv(manual_bets):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quotechar='"', quoting=csv.QUOTE_ALL, lineterminator="\n")

    writer.writerow([
        "Data", "Liga", "Jogo", "Mercado", "Odd", "Stake€",
        "Resultado", "Lucro€", "Notas", "Origem"
    ])

    for item in manual_bets or []:
        writer.writerow([
            normalize_date(item.get("data", "")),
            normalize_str(item.get("liga", "")),
            normalize_str(item.get("jogo", "")),
            normalize_str(item.get("mercado", "")).upper(),
            normalize_str(item.get("odd", "")),
            normalize_str(item.get("stake", "")),
            normalize_str(item.get("resultado", "")).upper(),
            "",
            normalize_str(item.get("notas", "")),
            "Manual",
        ])

    return output.getvalue()


@app.get("/")
def root():
    return jsonify({
        "ok": True,
        "service": "apostas-dashboard-sync",
        "endpoints": ["/health", "/state"],
        "repo": f"{GITHUB_OWNER}/{GITHUB_REPO}",
        "branch": GITHUB_BRANCH,
    })


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "apostas-dashboard-sync",
        "time": utc_now_iso(),
    })


@app.get("/state")
def get_state():
    try:
        content, _sha = get_file_from_github(STATE_PATH)

        if content is None:
            return jsonify({
                "ok": True,
                "exists": False,
                "state": dict(DEFAULT_STATE),
            })

        parsed = json.loads(content) if content.strip() else {}
        normalized = normalize_loaded_state(parsed)

        return jsonify({
            "ok": True,
            "exists": True,
            "state": normalized,
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

        manual_csv = manual_bets_to_csv(state.get("manualBets", []))
        _old_manual_content, manual_sha = get_file_from_github(MANUAL_BETS_PATH)
        put_file_to_github(
            MANUAL_BETS_PATH,
            manual_csv,
            "update manual bets csv",
            sha=manual_sha,
        )

        return jsonify({
            "ok": True,
            "state": state,
        })

    except Exception as e:
        print("POST /state error:", e, flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)
