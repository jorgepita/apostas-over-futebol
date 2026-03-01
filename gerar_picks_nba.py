# gerar_picks.py (NBA - OVER TOTAL only)
import base64
import json
import math
import os
from pathlib import Path
from urllib import request, parse, error
from datetime import datetime, timedelta

import pandas as pd

BASE = Path(__file__).resolve().parent

# =============================
# Anti-duplicados (por dia)
# =============================
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
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def pick_id(row: dict) -> str:
    # ID único (por dia) da pick
    # Date|League|Home|Away|Market|Line
    return (
        f"{row.get('Date','')}|{row.get('League','')}|"
        f"{row.get('HomeTeam','')}|{row.get('AwayTeam','')}|"
        f"{row.get('Market','')}|{row.get('Line','')}"
    )


# =============================
# Helpers matemáticos
# =============================
def safe_float(x, default=0.0) -> float:
    try:
        if x is None:
            return float(default)
        if isinstance(x, str):
            x = x.strip().replace(",", ".")
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return float(default)
        return v
    except Exception:
        return float(default)


def normal_cdf(z: float) -> float:
    # Φ(z)
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def prob_over_normal(mean_total: float, line: float, std: float) -> float:
    # P(Total > line) assumindo Normal(mean_total, std)
    # (com push ignorado; para line .5 não há push)
    if std <= 1e-9:
        return 1.0 if mean_total > line else 0.0
    z = (line - mean_total) / std
    return max(0.0, min(1.0, 1.0 - normal_cdf(z)))


def kelly_fraction(p: float, odd: float) -> float:
    if odd <= 1.0:
        return 0.0
    f = (p * odd - 1.0) / (odd - 1.0)
    return max(0.0, float(f))


# =============================
# Telegram
# =============================
def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
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
            f"{r.get('HomeTeam')} vs {r.get('AwayTeam')} | {r.get('Date')}\n"
            f"{r.get('Market')} {r.get('Line')} @ {r.get('Odd')}\n"
            f"Model: {safe_float(r.get('ProbModel')):.3f} | Market: {safe_float(r.get('ProbMarket')):.3f}\n"
            f"Edge: {safe_float(r.get('Edge')):.2%} | Stake: {safe_float(r.get('Stake€')):.2f}€\n\n"
        )
    return msg


# =============================
# GitHub upload (via API, sem git)
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


def github_put_file(
    owner: str,
    repo: str,
    path: str,
    content_bytes: bytes,
    branch: str,
    token: str,
    message: str,
) -> None:
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


def upload_csvs_to_github(files: list[Path], owner: str, repo: str, branch: str) -> None:
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
            msg = f"Update {fp.name} ({datetime.now(datetime.UTC).isoformat()}Z)"
            github_put_file(owner, repo, rel_path, content, branch, token, msg)
            ok += 1
        except Exception as e:
            print(f"GitHub: falhou upload de {fp.name} -> {e}")

    print(f"GitHub: upload concluído ({ok}/{len(files)} ficheiros).")


# =============================
# Regras de stakes (Over total)
# =============================
def apply_market_rules(rows: list[dict], bankroll: float, rules: dict) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    edge_min = float(rules.get("edge_min", 0.0))
    df = df[df["Edge"] >= edge_min].copy()
    if df.empty:
        return df

    kfrac = float(rules.get("kelly_fraction", 0.25))
    cap_frac = float(rules.get("cap_frac", 0.05))
    daily_cap_frac = float(rules.get("daily_cap_frac", 0.15))
    min_picks = int(rules.get("min_picks", 1))

    df["StakeFracRaw"] = df["KellyTrue"] * kfrac
    df["StakeFrac"] = df["StakeFracRaw"].clip(lower=0.0, upper=cap_frac)

    if len(df) < min_picks:
        return df.iloc[0:0].copy()

    total_frac = float(df["StakeFrac"].sum())
    scale = 1.0
    if total_frac > daily_cap_frac and total_frac > 0:
        scale = daily_cap_frac / total_frac
        df["StakeFrac"] = df["StakeFrac"] * scale

    df["Stake€"] = df["StakeFrac"] * float(bankroll)
    df["DailyScale"] = float(scale)
    df["Bankroll€"] = float(bankroll)

    df = df.sort_values(["Edge", "KellyTrue"], ascending=[False, False]).reset_index(drop=True)

    round_cols = {
        "MeanTotal": 2,
        "StdTotal": 2,
        "ProbModel": 4,
        "ProbMarket": 4,
        "Edge": 4,
        "KellyTrue": 4,
        "StakeFracRaw": 4,
        "StakeFrac": 4,
        "Stake€": 2,
        "Line": 1,
        "Odd": 2,
    }
    for col, dec in round_cols.items():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(dec)

    return df


# =============================
# NBA - histórico -> formato por equipa
# =============================
def build_team_game_log(df_hist: pd.DataFrame) -> pd.DataFrame:
    """
    Converte histórico (um row por jogo) para log por equipa (2 rows por jogo):
    Date, Team, Scored, Allowed
    """
    df = df_hist.copy()

    # Date robust
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).copy()

    # FTHG/FTAG robust
    df["FTHG"] = pd.to_numeric(df["FTHG"], errors="coerce")
    df["FTAG"] = pd.to_numeric(df["FTAG"], errors="coerce")
    df = df.dropna(subset=["FTHG", "FTAG", "HomeTeam", "AwayTeam"]).copy()

    home_rows = pd.DataFrame(
        {
            "Date": df["Date"],
            "Team": df["HomeTeam"].astype(str),
            "Scored": df["FTHG"],
            "Allowed": df["FTAG"],
        }
    )
    away_rows = pd.DataFrame(
        {
            "Date": df["Date"],
            "Team": df["AwayTeam"].astype(str),
            "Scored": df["FTAG"],
            "Allowed": df["FTHG"],
        }
    )

    games = pd.concat([home_rows, away_rows], ignore_index=True)
    games = games.sort_values(["Team", "Date"]).reset_index(drop=True)
    return games


def last_n_before(games: pd.DataFrame, team: str, dt: pd.Timestamp, n: int) -> pd.DataFrame:
    d = games[(games["Team"] == team) & (games["Date"] < dt)].sort_values("Date")
    return d.tail(n)


def expected_total_from_recent(
    games: pd.DataFrame,
    home: str,
    away: str,
    dt: pd.Timestamp,
    window: int,
    min_games: int,
) -> tuple[float, float, float, int, int]:
    """
    mean_total = expected_home + expected_away
    expected_home = avg(home_scored) & avg(away_allowed)
    expected_away = avg(away_scored) & avg(home_allowed)
    """
    h = last_n_before(games, home, dt, window)
    a = last_n_before(games, away, dt, window)

    h_n = len(h)
    a_n = len(a)
    if h_n < min_games or a_n < min_games:
        return 0.0, 0.0, 0.0, h_n, a_n

    h_sc = float(h["Scored"].mean())
    h_al = float(h["Allowed"].mean())
    a_sc = float(a["Scored"].mean())
    a_al = float(a["Allowed"].mean())

    exp_home = (h_sc + a_al) / 2.0
    exp_away = (a_sc + h_al) / 2.0
    mean_total = exp_home + exp_away
    return exp_home, exp_away, mean_total, h_n, a_n


# =============================
# Main
# =============================
def main():
    cfg_path = BASE / "config.json"
    if not cfg_path.exists():
        raise SystemExit("Falta config.json na pasta do projeto.")

    cfg_text = cfg_path.read_text(encoding="utf-8").strip()
    cfg = json.loads(cfg_text)

    fixtures_path = BASE / "fixtures_today.csv"
    if not fixtures_path.exists():
        raise SystemExit("Falta fixtures_today.csv na pasta do projeto.")

    # read fixtures robust
    fixtures = pd.read_csv(fixtures_path, sep=None, engine="python")

    print("[DBG] GERAR_PICKS NBA START v1")
    print("[DBG] fixtures cols:", list(fixtures.columns))

    # Detect columns
    def pick_col(cands: list[str]) -> str | None:
        for c in cands:
            if c in fixtures.columns:
                return c
        return None

    col_date = pick_col(["Date", "date"])
    col_league = pick_col(["League", "league"])
    col_home = pick_col(["HomeTeam", "home", "home_team", "Home"])
    col_away = pick_col(["AwayTeam", "away", "away_team", "Away"])

    col_line = pick_col(["Line", "line", "TotalLine", "total_line", "Total", "total"])
    col_odd = pick_col(["Odd_Over", "odd_over", "OddOver", "odd", "OverOdd", "over_odd"])

    required = [col_date, col_home, col_away, col_line, col_odd]
    if any(x is None for x in required):
        raise SystemExit(
            "fixtures_today.csv precisa de colunas (mínimo): Date, HomeTeam, AwayTeam, Line, Odd_Over"
        )

    if col_league is None:
        fixtures["League"] = "nba"
        col_league = "League"

    # Date -> date
    fixtures[col_date] = pd.to_datetime(fixtures[col_date], errors="coerce").dt.date
    fixtures = fixtures.dropna(subset=[col_date]).copy()

    # timezone Lisboa (para filtro de datas)
    try:
        from zoneinfo import ZoneInfo
        now_pt = datetime.now(ZoneInfo("Europe/Lisbon"))
    except Exception:
        now_pt = datetime.utcnow()

    days_ahead = int(cfg.get("run", {}).get("days_ahead", 1))
    start = now_pt.date()
    end = start + timedelta(days=days_ahead)
    today_iso = start.isoformat()

    fixtures = fixtures[(fixtures[col_date] >= start) & (fixtures[col_date] <= end)].copy()

    # normalize columns
    fixtures["Date"] = fixtures[col_date].astype(str)
    fixtures["League"] = fixtures[col_league].astype(str)
    fixtures["HomeTeam"] = fixtures[col_home].astype(str)
    fixtures["AwayTeam"] = fixtures[col_away].astype(str)
    fixtures["Line"] = fixtures[col_line].apply(lambda x: safe_float(x, 0.0))
    fixtures["Odd"] = fixtures[col_odd].apply(lambda x: safe_float(x, 0.0))

    fixtures = fixtures[(fixtures["Line"] > 0) & (fixtures["Odd"] > 1.0)].copy()

    print("[DBG] fixtures rows after date+odds filter:", len(fixtures))
    if len(fixtures) == 0:
        # ainda assim cria ficheiros vazios
        out_path = BASE / "picks_over.csv"
        combo_path = BASE / "picks_hoje.csv"
        pd.DataFrame().to_csv(out_path, index=False, encoding="utf-8", sep=";")
        pd.DataFrame().to_csv(combo_path, index=False, encoding="utf-8", sep=";")
        print("OK. Sem fixtures válidos.")
        return

    # Load NBA history
    hist_cfg = cfg.get("history", {})
    window = int(hist_cfg.get("window", 15))
    min_games = int(hist_cfg.get("min_games", 8))
    std_total = float(hist_cfg.get("std_total", 14.0))

    hist_path = BASE / "data_raw" / "nba.csv"
    if not hist_path.exists():
        raise SystemExit("Falta data_raw/nba.csv (histórico NBA).")

    df_hist = pd.read_csv(hist_path, sep=None, engine="python")
    need_hist = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    if not need_hist.issubset(set(df_hist.columns)):
        raise SystemExit(f"nba.csv precisa colunas: {sorted(need_hist)}")

    games = build_team_game_log(df_hist)

    rows = []

    for _, fx in fixtures.iterrows():
        home = fx["HomeTeam"]
        away = fx["AwayTeam"]
        line = float(fx["Line"])
        odd = float(fx["Odd"])

        dt = pd.to_datetime(fx["Date"], errors="coerce")
        if pd.isna(dt):
            continue

        exp_h, exp_a, mean_total, h_n, a_n = expected_total_from_recent(
            games, home, away, dt, window=window, min_games=min_games
        )
        if mean_total <= 0:
            continue

        p_over = prob_over_normal(mean_total, line, std_total)
        p_mkt = (1.0 / odd) if odd > 1.0 else 0.0
        edge = p_over - p_mkt
        k = kelly_fraction(p_over, odd)

        # debug curto
        print(
            f"[DBG] {home} vs {away} | line={line:.1f} odd={odd:.2f} "
            f"mean={mean_total:.1f} std={std_total:.1f} "
            f"p={p_over:.3f} pm={p_mkt:.3f} edge={edge:.3f} "
            f"hN={h_n} aN={a_n}"
        )

        rows.append(
            {
                "Date": fx["Date"],
                "League": fx["League"],
                "HomeTeam": home,
                "AwayTeam": away,
                "Market": "OVER",
                "Line": line,
                "Odd": odd,
                "ExpHome": exp_h,
                "ExpAway": exp_a,
                "MeanTotal": mean_total,
                "StdTotal": std_total,
                "ProbModel": p_over,
                "ProbMarket": p_mkt,
                "Edge": edge,
                "KellyTrue": k,
                "Window": window,
                "MinGames": min_games,
                "HomeGamesUsed": h_n,
                "AwayGamesUsed": a_n,
            }
        )

    print(f"[DBG] PRE-FILTER OVER: rows={len(rows)}")

    bankroll_cfg = cfg.get("bankroll", {})
    rules_cfg = cfg.get("rules", {})

    bankroll = float(bankroll_cfg.get("over", 0.0))
    out = apply_market_rules(rows, bankroll, rules_cfg.get("over", {}))

    out_path = BASE / "picks_over.csv"
    combo_path = BASE / "picks_hoje.csv"

    out.to_csv(out_path, index=False, encoding="utf-8", sep=";")
    out.to_csv(combo_path, index=False, encoding="utf-8", sep=";")

    print("OK. Gerados:")
    print(f"- {out_path.name} ({len(out)} picks)")
    print(f"- {combo_path.name} ({len(out)} picks)")

    # ==========================
    # Telegram (anti-duplicados por dia)
    # ==========================
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
    CHAT_ID = os.getenv("CHAT_ID", "").strip()

    if TELEGRAM_TOKEN and CHAT_ID:
        try:
            sent = load_sent_state(today_iso)

            new_rows = []
            for r in df_to_rows(out):
                pid = pick_id(r)
                if pid not in sent:
                    new_rows.append(r)

            msg = build_message(new_rows, "PICKS NBA OVER (NOVAS)")
            if msg:
                _send_in_chunks(TELEGRAM_TOKEN, CHAT_ID, msg, "NBA OVER")
                for r in new_rows:
                    sent.add(pick_id(r))
                save_sent_state(today_iso, sent)
                print(f"Telegram: enviei {len(new_rows)} novas.")
            else:
                print("Telegram: sem novas picks (não enviei).")
        except Exception as e:
            print(f"Telegram: erro ao enviar -> {e}")
    else:
        print("Telegram: TOKEN ou CHAT_ID em falta (não enviei mensagem).")

    # ==========================
    # GitHub: upload dos CSVs gerados
    # ==========================
    owner = "jorgepita"
    repo = "apostas-over-futebol"
    branch = "main"
    upload_csvs_to_github([out_path, combo_path], owner, repo, branch)


if __name__ == "__main__":
    main()
