import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SENT_STATE_PATH = BASE / "sent_state.json"


def load_sent_state(today_iso: str) -> set[str]:
    try:
        if not SENT_STATE_PATH.exists():
            return set()
        data = json.loads(SENT_STATE_PATH.read_text(encoding="utf-8"))
        if data.get("date") != today_iso:
            return set()
        sent_list = data.get("sent", [])
        return set(sent_list) if isinstance(sent_list, list) else set()
    except Exception:
        return set()


def save_sent_state(today_iso: str, sent: set[str]) -> None:
    payload = {"date": today_iso, "sent": sorted(sent)}
    SENT_STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def pick_id(row: dict) -> str:
    return f"{row['Date']}|{row['League']}|{row['HomeTeam']}|{row['AwayTeam']}|{row['Market']}"
