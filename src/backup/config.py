"""
src/backup/config.py

Backup subsystem configuration — the files to protect and retention caps
come from config.json["backup"] (operator-editable, same as every other
tunable in this project); Cloudflare R2 connection settings come from
environment variables only, never config.json — the same secret/config
separation this project already applies to GITHUB_TOKEN/API_FOOTBALL_KEY
etc. See docs/09_Architecture_Decisions.md ADR-020 and its Phase 27.3
"Production Hardening" addendum.

Configuration sources, in the order Python's `os.environ` naturally
resolves them (this module does not implement its own precedence logic —
whichever value is actually in the process environment when `get_r2_settings()`
runs wins):

- **Railway** — real environment variables set in the Railway dashboard.
  No `.env` file exists on Railway; `load_dotenv()` below is a no-op there.
- **GitHub Actions** — `${{ secrets.R2_* }}` injected as job-step `env:`
  entries (see `.github/workflows/bot.yml`). Also no `.env` file; also a
  no-op.
- **Local development** — `load_dotenv()` (python-dotenv) reads a local,
  gitignored `.env` file (see `.env.example` for the full variable list,
  committed with placeholder-only values — never real credentials) and
  fills in any variable not already present in the process environment.
  `load_dotenv()` never overrides a variable that's already set, so this
  is safe to call unconditionally on all three platforms.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_BACKUP_FILES = [
    "cloud_state.json",
    "picks_history.csv",
    "picks_hoje.csv",
    "picks_hoje_github.csv",
    "picks_hoje_simplificado.csv",
    "picks_over25.csv",
    "picks_btts.csv",
    "league_stats.csv",
    "sent_state.json",
]

DEFAULT_SCHEDULED_MAX_COUNT = 60
DEFAULT_MANUAL_MAX_AGE_DAYS = 90
DEFAULT_CRITICAL_MAX_COUNT = None  # unlimited by default — see backup_retention.py


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_backup_config(base_path: Path | None = None) -> dict:
    """Mirrors src/config.py::get_void_policy()'s defensive-fallback style:
    a missing or malformed config.json["backup"] block never disables the
    backup subsystem — it just falls back to these documented defaults."""
    cfg = {}
    cfg_path = Path(base_path or _project_root()) / "config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8")).get("backup", {}) or {}
        except (json.JSONDecodeError, OSError):
            cfg = {}

    files = cfg.get("files")
    if not isinstance(files, list) or not files:
        files = DEFAULT_BACKUP_FILES

    retention_raw = cfg.get("retention", {}) or {}

    def _positive_int_or_none(value, default):
        # A missing key (value is None) or an invalid one both fall back to
        # `default` — for critical_max_count that default is itself None
        # (unlimited), so an absent key and an explicit `null` in
        # config.json behave identically, which is the intended semantic.
        try:
            v = int(value)
            return v if v > 0 else default
        except (TypeError, ValueError):
            return default

    def _positive_number(value, default):
        try:
            v = float(value)
            return v if v > 0 else default
        except (TypeError, ValueError):
            return default

    return {
        "enabled": bool(cfg.get("enabled", True)),
        "files": files,
        "retention": {
            "scheduled_max_count": _positive_int_or_none(
                retention_raw.get("scheduled_max_count"), DEFAULT_SCHEDULED_MAX_COUNT),
            "manual_max_age_days": _positive_number(
                retention_raw.get("manual_max_age_days"), DEFAULT_MANUAL_MAX_AGE_DAYS),
            "critical_max_count": _positive_int_or_none(
                retention_raw.get("critical_max_count"), DEFAULT_CRITICAL_MAX_COUNT),
        },
    }


DEFAULT_R2_REGION = "auto"  # Cloudflare R2's own documented value for its S3-compatible API
DEFAULT_R2_CONNECT_TIMEOUT_SECONDS = 10
DEFAULT_R2_READ_TIMEOUT_SECONDS = 60
DEFAULT_R2_MAX_RETRY_ATTEMPTS = 3


def _positive_number_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        v = float(raw)
        return v if v > 0 else default
    except ValueError:
        return default


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except ValueError:
        return default


def get_r2_settings() -> dict:
    """Every value here comes from an environment variable only — see this
    module's docstring for the three supported sources (Railway, GitHub
    Actions secrets, local `.env`). A missing or malformed numeric value
    (timeouts, retry count) falls back to its documented default rather
    than raising or silently becoming 0/negative — the same per-key
    defensive style `get_backup_config()`/`src/config.py::get_void_policy()`
    already use elsewhere in this project."""
    return {
        "enabled": os.getenv("R2_ENABLED", "").strip().lower() in ("1", "true", "yes"),
        "account_id": os.getenv("R2_ACCOUNT_ID", "").strip(),
        "endpoint_url": os.getenv("R2_ENDPOINT_URL", "").strip(),
        "access_key_id": os.getenv("R2_ACCESS_KEY_ID", "").strip(),
        "secret_access_key": os.getenv("R2_SECRET_ACCESS_KEY", "").strip(),
        "bucket": os.getenv("R2_BUCKET_NAME", "").strip(),
        "region": os.getenv("R2_REGION", "").strip() or DEFAULT_R2_REGION,
        "connect_timeout_seconds": _positive_number_env(
            "R2_CONNECT_TIMEOUT_SECONDS", DEFAULT_R2_CONNECT_TIMEOUT_SECONDS),
        "read_timeout_seconds": _positive_number_env(
            "R2_READ_TIMEOUT_SECONDS", DEFAULT_R2_READ_TIMEOUT_SECONDS),
        "max_retry_attempts": _positive_int_env(
            "R2_MAX_RETRY_ATTEMPTS", DEFAULT_R2_MAX_RETRY_ATTEMPTS),
    }
