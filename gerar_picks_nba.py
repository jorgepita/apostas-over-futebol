# gerar_picks_nba.py (NBA - OVER, com fixtures_today_nba.csv)
import base64
import json
import math
import os
from pathlib import Path
from urllib import request, parse, error
from datetime import datetime, timedelta, timezone

import pandas as pd

BASE = Path(__file__).resolve().parent

# =============================
# Anti-duplicados (por dia)
# =============================
SENT_STATE_PATH = BASE / "sent_state_nba.json"


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
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def pick_id(row: dict) -> str:
    # Date|Home|Away|Line|Book
    return (
        f"{row.get('Date','')}|{row.get('HomeTeam','')}|{row.get('AwayTeam','')}|"
        f"{row.get('Line','')}|{row.get('Book','')}"
    )


# =============================
# Helpers
# =============================
def safe_mean(series) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        return 0.0
    return float(s.mean())


def normal_cdf(x: float, mu: float, sigma: float) -> float:
    if sigma <= 1e-9:
        return 1.0 if x >= mu else 0.0
    z = (x - mu) / (sigma * math.sqrt(2.0))
    return 0.5 * (1.0 + math.erf(z))


def prob_over_normal(mu_total: float, line: float, std_total: float) -> float:
    # P(total > line) = 1 - CDF(line)
    p = 1.0 - normal_cdf(line, mu_total, std_total)
    return float(min(1.0, max(0.0, p)))


def kelly_fraction(p: float, odd: float) -> float:
    if odd is None or odd <= 1.0:
        return 0.0
    f = (p * odd - 1.0) / (odd - 1.0)
    return max(0.0, float(f))


# =============================
# Modelo NBA (window=15)
# =============================
def league_avgs_points(df_hist: pd.DataFrame) -> tuple[float, float]:
    return (
        safe_mean(df_hist.get("FTHG", pd.Series(dtype=float))),
        safe_mean(df_hist.get("FTAG", pd.Series(dtype=float))),
    )


def last_n_home(df_hist: pd.DataFrame, team: str, n: int) -> pd.DataFrame:
    d = df_hist[df_hist["HomeTeam"] == team].sort_values("Date")
    return d.tail(n)


def last_n_away(df_hist: pd.DataFrame, team: str, n: int) -> pd.DataFrame:
    d = df_hist[df_hist["AwayTeam"] == team].sort_values("Date")
    return d.tail(n)


def compute_expected_total(
    df_hist: pd.DataFrame,
    home: str,
    away: str,
    window: int,
    min_games_home: int,
    min_games_away: int,
    shrink: float,
) -> tuple[float, float, float, int, int]:
    """
    Retorna: (mu_home, mu_away, mu_total, h_n, a_n)
    Modelo por rácios ataque/defesa com shrink.
    """
    avg_home, avg_away = league_avgs_points(df_hist)
    if avg_home <= 0:
        avg_home = 112.0
    if avg_away <= 0:
        avg_away = 110.0

    h_last = last_n_home(df_hist, home, window)
    a_last = last_n_away(df_hist, away, window)

    h_n = len(h_last)
    a_n = len(a_last)

    # neutros
    home_attack = 1.0
    home_def = 1.0
    away_attack = 1.0
    away_def = 1.0

    if h_n >= max(1, min_games_home):
        h_scored = safe_mean(h_last["FTHG"])
        h_conc = safe_mean(h_last["FTAG"])
        home_attack = (h_scored / avg_home) if avg_home > 0 else 1.0
        home_def = (h_conc / avg_away) if avg_away > 0 else 1.0
        home_attack = 1.0 + shrink * (home_attack - 1.0)
        home_def = 1.0 + shrink * (home_def - 1.0)

    if a_n >= max(1, min_games_away):
        a_scored = safe_mean(a_last["FTAG"])
        a_conc = safe_mean(a_last["FTHG"])
        away_attack = (a_scored / avg_away) if avg_away > 0 else 1.0
        away_def = (a_conc / avg_home) if avg_home > 0 else 1.0
        away_attack = 1.0 + shrink * (away_attack - 1.0)
        away_def = 1.0 + shrink * (away_def - 1.0)

    mu_home = avg_home * home_attack * away_def
    mu_away = avg_away * away_attack * home_def

    mu_home = float(max(80.0, min(140.0, mu_home)))
    mu_away = float(max(80.0, min(140.0, mu_away)))
    mu_total = mu_home + mu_away
    return mu_home, mu_away, mu_total, h_n, a_n


# =============================
# Regras / stakes
# =============================
def apply_rules(rows: list[dict], bankroll: float, rules: dict) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    edge_min = float(rules.get("edge_min", 0.0))
    min_odd = float(rules.get("min_odd", 1.01))
    max_picks = int(rules.get("max_picks", 10))

    df = df[df["Edge"] >= edge_min].copy()
    df = df[df["Odd"] >= min_odd].copy()
    if df.empty:
        return df

    # ordenar e cortar
    df = df.sort_values(["Edge", "KellyTrue"], ascending=[False, False]).head(max_picks).copy()

    kfrac = float(rules.get("kelly_fraction", 0.25))
    cap_frac = float(rules.get("cap_frac", 0.05))
    daily_cap_frac = float(rules.get("daily_cap_frac", 0.15))

    df["StakeFracRaw"] = df["KellyTrue"] * kfrac
    df["StakeFrac"] = df["StakeFracRaw"].clip(lower=0.0, upper=cap_frac)

    total_frac = float(df["StakeFrac"].sum())
    scale = 1.0
    if total_frac > daily_cap_frac and total_frac > 0:
        scale = daily_cap_frac / total_frac
        df["StakeFrac"] = df["StakeFrac"] * scale

    df["Stake€"] = df["StakeFrac"] * float(bankroll)
    df["DailyScale"] = float(scale)
    df["Bankroll€"] = float(bankroll)

    # arredondar
    round_cols = {
        "MuHome": 2,
        "MuAway": 2,
        "MuTotal": 2,
        "StdTotal": 2,
        "ProbModel": 4,
        "ProbMarket": 4,
        "Edge": 4,
        "KellyTrue": 4,
        "StakeFrac": 4,
        "Stake€": 2,
        "Odd": 2,
        "Line": 1,
    }
    for col, dec in round_cols.items():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(dec)

    return df.reset_index(drop=True)


# =============================
# Telegram
# =============================
def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode("utf-8")
    req = request.Request(url, data=data, method="POST")
    with request.urlopen(req, timeout=20) as resp:
        _ = resp.read()


def _send_in_chunks(token: str, chat_id: str, text: str, title: str) -> None:
    MAX = 3900
    if not text:
        return
    if len(text) <= MAX:
        send_telegram_message(token, chat_id, text)
        return

    parts = []
    cur = ""
    for line in text.splitlines(True):
        if len(cur) + len(line) > MAX:
            parts.append(cur)
            cur = ""
        cur += line
    if cur:
        parts.append(cur)

    for i, p in enumerate(parts, 1):
        prefix = f"{title} ({i}/{len(parts)})\n"
        send_telegram_message(token, chat_id, prefix + p)


def df_to_rows(df: pd.DataFrame) -> list[dict]:
    if df is None or len(df) == 0:
        return []
    return df.to_dict(orient="records")


def build_message(rows: list[dict], titulo: str) -> str:
    if not rows:
        return ""
    msg = f"🏀 {titulo}\n\n"
    for r in rows:
        msg += (
            f"NBA | {r['AwayTeam']} @ {r['HomeTeam']} | {r['Date']}\n"
            f"OVER {r['Line']} @ {r['Odd']} ({r.get('Book','')})\n"
            f"Model {float(r['ProbModel']):.1%} | Market {float(r['ProbMarket']):.1%}\n"
            f"Edge {float(r['Edge']):.1%} | Stake {float(r.get('Stake€', 0.0)):.2f}€\n\n"
        )
    return msg


# =============================
# GitHub upload (via API)
# =============================
def github_request(url: str, token: str, method: str = "GET", data: dict | None = None):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"token {token}",
        "User-Agent": "render-apostas-bot",
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url, data=body, headers=headers, method=method)
    with request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def github_get_sha(owner: str, repo: str, path: str, branch: str, token: str) -> str | None:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{parse.quote(path)}?ref={parse.quote(branch)}"
    try:
        j = github_request(url, token, method="GET")
        sha = j.get("sha")
        return sha if isinstance(sha, str) else None
    except error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def github_put_file(owner: str, repo: str, path: str, content_bytes: bytes, branch: str, token: str, message: str) -> None:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{parse.quote(path)}"
    sha = github_get_sha(owner, repo, path, branch, token)

    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    _ = github_request(url, token, method="PUT", data=payload)


def upload_files_to_github(files: list[Path], owner: str, repo: str, branch: str) -> None:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        print("GitHub: GITHUB_TOKEN em falta (não fiz upload).")
        return

    prefix = os.getenv("GITHUB_PATH_PREFIX", "").strip().strip("/")
    ok = 0
    for fp in files:
        if not fp.exists():
            continue

        rel_path = fp.name if not prefix else f"{prefix}/{fp.name}"

        try:
            content = fp.read_bytes()
            msg = f"Update {fp.name} ({datetime.now(timezone.utc).isoformat()})"
            github_put_file(owner, repo, rel_path, content, branch, token, msg)
            ok += 1
        except Exception as e:
            print(f"GitHub: falhou upload de {fp.name} -> {e}")

    print(f"GitHub: upload concluído ({ok}/{len(files)} ficheiros).")


# =============================
# Main
# =============================
def main():
    cfg_path = BASE / "config.json"
    if not cfg_path.exists():
        raise SystemExit("Falta config.json na pasta do projeto.")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    # Lê fixtures NBA
    fx_path = BASE / "fixtures_today_nba.csv"
    if not fx_path.exists():
        raise SystemExit("Falta fixtures_today_nba.csv (corre fetch_fixtures_nba.py primeiro).")

    fx = pd.read_csv(fx_path, sep=None, engine="python")
    need_fx = {"Date", "League", "HomeTeam", "AwayTeam", "Book", "Line", "Odd"}
    if not need_fx.issubset(set(fx.columns)):
        raise SystemExit(f"fixtures_today_nba.csv precisa colunas: {sorted(need_fx)}")

    # Filtro NBA
    fx["League"] = fx["League"].astype(str).str.lower()
    fx = fx[fx["League"].isin(["nba", "basketball_nba"])].copy()

    # Date -> date
    fx["Date"] = pd.to_datetime(fx["Date"], errors="coerce").dt.date
    fx = fx.dropna(subset=["Date"]).copy()

    # Janela de dias (hoje..hoje+days_ahead)
    days_ahead = int(cfg.get("run", {}).get("days_ahead", 1))
    today = datetime.now(timezone.utc).date()
    end = today + timedelta(days=days_ahead)
    today_iso = today.isoformat()

    fx = fx[(fx["Date"] >= today) & (fx["Date"] <= end)].copy()
    fx["Date"] = fx["Date"].astype(str)

    print("[DBG] NBA FIXTURES rows:", len(fx))
    if fx.empty:
        raise SystemExit("Sem fixtures NBA no range (hoje..days_ahead).")

    # Histórico NBA
    hist_path = BASE / "data_raw" / "nba.csv"
    if not hist_path.exists():
        raise SystemExit("Falta data_raw/nba.csv (histórico).")

    df_hist = pd.read_csv(hist_path, sep=None, engine="python")
    need_hist = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    if not need_hist.issubset(set(df_hist.columns)):
        raise SystemExit(f"nba.csv precisa colunas: {sorted(need_hist)}")

    df_hist["Date"] = pd.to_datetime(df_hist["Date"], errors="coerce")
    df_hist = df_hist.dropna(subset=["Date"]).copy()

    model_cfg = cfg.get("model", {})
    window = int(model_cfg.get("window", 15))
    min_games_home = int(model_cfg.get("min_games_home", 8))
    min_games_away = int(model_cfg.get("min_games_away", 8))
    shrink = float(model_cfg.get("shrink", 0.75))
    std_total = float(model_cfg.get("std_total", 14.0))
    mu_boost = float(model_cfg.get("mu_boost", 1.0))

    bankroll = float(cfg.get("bankroll", {}).get("nba_over", 0.0))
    rules = cfg.get("rules", {}).get("nba_over", {})

    # Agrupar por jogo e escolher melhor linha (maior Edge)
    best_by_game: dict[tuple[str, str, str], dict] = {}

    for _, r in fx.iterrows():
        home = str(r["HomeTeam"]).strip()
        away = str(r["AwayTeam"]).strip()
        date_iso = str(r["Date"]).strip()

        try:
            line = float(r["Line"])
            odd = float(r["Odd"])
        except Exception:
            continue

        if odd <= 1.0:
            continue

        mu_h, mu_a, mu_t, h_n, a_n = compute_expected_total(
            df_hist, home, away, window, min_games_home, min_games_away, shrink
        )

        if mu_boost and mu_boost != 1.0:
            mu_t = mu_t * mu_boost

        p_model = prob_over_normal(mu_t, line, std_total)
        p_market = (1.0 / odd) if odd > 1.0 else 0.0
        edge = p_model - p_market
        ktrue = kelly_fraction(p_model, odd)

        cand = {
            "Date": date_iso,
            "League": "nba",
            "HomeTeam": home,
            "AwayTeam": away,
            "Book": str(r["Book"]),
            "Market": "OVER",
            "Line": line,
            "Odd": odd,
            "MuHome": mu_h,
            "MuAway": mu_a,
            "MuTotal": mu_t,
            "StdTotal": std_total,
            "ProbModel": p_model,
            "ProbMarket": p_market,
            "Edge": edge,
            "KellyTrue": ktrue,
            "HomeGamesUsed": h_n,
            "AwayGamesUsed": a_n,
        }

        key = (date_iso, home, away)
        prev = best_by_game.get(key)
        if prev is None or cand["Edge"] > prev["Edge"]:
            best_by_game[key] = cand

    rows = list(best_by_game.values())

    print(f"[DBG] PRE-FILTER unique games={len(rows)}")
    if rows:
        print(f"[DBG] edge_max={max(x['Edge'] for x in rows):.4f} edge_min={min(x['Edge'] for x in rows):.4f}")

    out = apply_rules(rows, bankroll, rules)

    out_path = BASE / "picks_nba_over.csv"
    combo_path = BASE / "picks_hoje.csv"

    out.to_csv(out_path, index=False, encoding="utf-8", sep=";")
    out.to_csv(combo_path, index=False, encoding="utf-8", sep=";")

    print("OK. Gerados:")
    print(f"- {out_path.name} ({len(out)} picks)")
    print(f"- {combo_path.name} ({len(out)} picks)")

    # Telegram
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
    CHAT_ID = os.getenv("CHAT_ID", "").strip()

    if TELEGRAM_TOKEN and CHAT_ID:
        try:
            sent = load_sent_state(today_iso)
            new_rows = []
            for rr in df_to_rows(out):
                pid = pick_id(rr)
                if pid not in sent:
                    new_rows.append(rr)

            msg = build_message(new_rows, "PICKS NBA OVER (NOVAS)")
            if msg:
                _send_in_chunks(TELEGRAM_TOKEN, CHAT_ID, msg, "NBA OVER")

            for rr in new_rows:
                sent.add(pick_id(rr))
            save_sent_state(today_iso, sent)

            if msg:
                print(f"Telegram: enviei {len(new_rows)} novas.")
            else:
                print("Telegram: sem novas picks (não enviei).")
        except Exception as e:
            print(f"Telegram: erro ao enviar -> {e}")
    else:
        print("Telegram: TOKEN ou CHAT_ID em falta (não enviei mensagem).")

    # GitHub upload
    owner = "jorgepita"
    repo = "apostas-over-futebol"
    branch = "main"
    upload_files_to_github([out_path, combo_path], owner, repo, branch)


if __name__ == "__main__":
    main()
