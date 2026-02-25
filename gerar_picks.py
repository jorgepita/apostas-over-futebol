# gerar_picks.py
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
    """
    Lê o estado {date, sent[]} e devolve set(ids).
    Se a data guardada for diferente de hoje, reseta.
    """
    try:
        if not SENT_STATE_PATH.exists():
            return set()
        data = json.loads(SENT_STATE_PATH.read_text(encoding="utf-8"))
        if data.get("date") != today_iso:
            return set()
        sent_list = data.get("sent", [])
        return set(sent_list) if isinstance(sent_list, list) else set()
    except Exception:
        # se o ficheiro corromper, recomeça
        return set()


def save_sent_state(today_iso: str, sent: set[str]) -> None:
    payload = {"date": today_iso, "sent": sorted(sent)}
    SENT_STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def pick_id(row: dict) -> str:
    """
    ID único da pick (por dia): Date|League|Home|Away|Market
    """
    return f"{row['Date']}|{row['League']}|{row['HomeTeam']}|{row['AwayTeam']}|{row['Market']}"


# =============================
# Helpers estatísticos / modelo
# =============================
def safe_mean(series) -> float:
    if series is None:
        return 0.0
    try:
        if len(series) == 0:
            return 0.0
    except Exception:
        return 0.0
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        return 0.0
    return float(s.mean())


def poisson_cdf(k: int, lam: float) -> float:
    """P(X <= k) para X ~ Poisson(lam)."""
    if lam <= 0:
        return 1.0 if k >= 0 else 0.0
    term = math.exp(-lam)
    s = term
    for i in range(1, k + 1):
        term *= lam / i
        s += term
    return float(min(1.0, max(0.0, s)))


def prob_over_line(lam_total: float, line: float) -> float:
    """
    Para total goals ~ Poisson(lam_total).
    Over 1.5 => >=2 => 1 - P(X<=1)
    Over 2.5 => >=3 => 1 - P(X<=2)
    """
    k = int(math.floor(line))
    return 1.0 - poisson_cdf(k, lam_total)


def kelly_fraction(p: float, odd: float) -> float:
    """Kelly "true": f = (p*odd - 1)/(odd-1), com piso 0."""
    if odd is None or odd <= 1.0:
        return 0.0
    f = (p * odd - 1.0) / (odd - 1.0)
    return max(0.0, float(f))


def league_avgs(df_hist: pd.DataFrame) -> tuple[float, float]:
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


def compute_lambdas(df_hist: pd.DataFrame, home: str, away: str, window: int) -> tuple[float, float, float]:
    avg_home, avg_away = league_avgs(df_hist)
    if avg_home <= 0:
        avg_home = 1.2
    if avg_away <= 0:
        avg_away = 1.0

    h_last = last_n_home(df_hist, home, window)
    a_last = last_n_away(df_hist, away, window)

    # neutros por defeito
    home_attack = 1.0
    home_defense = 1.0
    away_attack = 1.0
    away_defense = 1.0

    if h_last is not None and len(h_last) > 0:
        home_scored = safe_mean(h_last.get("FTHG", pd.Series(dtype=float)))
        home_conceded = safe_mean(h_last.get("FTAG", pd.Series(dtype=float)))
        if home_scored > 0:
            home_attack = home_scored / avg_home if avg_home > 0 else 1.0
        if home_conceded > 0:
            home_defense = home_conceded / avg_away if avg_away > 0 else 1.0

    if a_last is not None and len(a_last) > 0:
        away_scored = safe_mean(a_last.get("FTAG", pd.Series(dtype=float)))
        away_conceded = safe_mean(a_last.get("FTHG", pd.Series(dtype=float)))
        if away_scored > 0:
            away_attack = away_scored / avg_away if avg_away > 0 else 1.0
        if away_conceded > 0:
            away_defense = away_conceded / avg_home if avg_home > 0 else 1.0

    lam_home = avg_home * home_attack * away_defense
    lam_away = avg_away * away_attack * home_defense

    lam_home = float(max(0.05, min(6.0, lam_home)))
    lam_away = float(max(0.05, min(6.0, lam_away)))
    return lam_home, lam_away, lam_home + lam_away


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
    msg = f"📊 {titulo}\n\n"
    for r in rows:
        msg += (
            f"{r['LeagueName']} | {r['HomeTeam']} vs {r['AwayTeam']}\n"
            f"Market: {r['Market']} @ {r['Odd']}\n"
            f"Edge: {float(r['Edge']):.2%} | Stake: {float(r.get('Stake€', 0.0)):.2f}€\n\n"
        )
    return msg


# =============================
# Regras de mercado / stakes
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

    df = df.sort_values(["Edge", "KellyTrue"], ascending=[False, False]).reset_index(
        drop=True
    )

    round_cols = {
        "LambdaHome": 3,
        "LambdaAway": 3,
        "LambdaTotal": 3,
        "ProbModel": 3,
        "ProbMarket": 3,
        "Edge": 4,
        "KellyTrue": 4,
        "StakeFracRaw": 4,
        "StakeFrac": 4,
        "Stake€": 2,
    }
    for col, dec in round_cols.items():
        if col in df.columns:
            df[col] = df[col].round(dec)

    return df


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
    # exemplo: se quiseres meter em pasta "out", defines GITHUB_PATH_PREFIX=out

    ok = 0
    for fp in files:
        if not fp.exists():
            continue

        rel_path = fp.name if not prefix else f"{prefix}/{fp.name}"

        try:
            content = fp.read_bytes()
            msg = f"Update {fp.name} ({datetime.utcnow().isoformat()}Z)"
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

    fixtures_path = BASE / "fixtures_today.csv"
    if not fixtures_path.exists():
        raise SystemExit("Falta fixtures_today.csv na pasta do projeto.")

    # Robust: tenta detetar separador (vírgula/;), sem rebentar
    fixtures = pd.read_csv(fixtures_path, sep=None, engine="python")

    required = {"Date", "League", "HomeTeam", "AwayTeam", "Odd_Over15", "Odd_Over25"}
    if not required.issubset(set(fixtures.columns)):
        raise SystemExit(f"fixtures_today.csv precisa das colunas: {sorted(required)}")

    # Date -> date
    fixtures["Date"] = pd.to_datetime(fixtures["Date"], errors="coerce").dt.date
    fixtures = fixtures.dropna(subset=["Date"]).copy()

    # Timezone "Portugal" (Lisboa)
    try:
        from zoneinfo import ZoneInfo

        now_pt = datetime.now(ZoneInfo("Europe/Lisbon"))
    except Exception:
        now_pt = datetime.utcnow()

    days_ahead = int(cfg.get("run", {}).get("days_ahead", 1))  # default 1 dia
    start = now_pt.date()
    end = start + timedelta(days=days_ahead)
    today_iso = start.isoformat()

    # manter jogos entre hoje e hoje+days_ahead (inclusive)
    fixtures = fixtures[(fixtures["Date"] >= start) & (fixtures["Date"] <= end)].copy()

    # guardar Date em string ISO
    fixtures["Date"] = fixtures["Date"].astype(str)

    rows15, rows25 = [], []

    history_cfg = cfg.get("history", {})
    window = int(history_cfg.get("window", 10))

    leagues_cfg = cfg.get("leagues", {})
    for league_key, league_meta in leagues_cfg.items():
        league_fixt = fixtures[fixtures["League"] == league_key].copy()
        if league_fixt.empty:
            continue

        hist_path = BASE / "data_raw" / f"{league_key}.csv"
        if not hist_path.exists():
            continue

        df_hist = pd.read_csv(hist_path, sep=None, engine="python")

        need_hist = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
        if not need_hist.issubset(set(df_hist.columns)):
            continue

        df_hist["Date"] = pd.to_datetime(df_hist["Date"], dayfirst=True, errors="coerce")
        df_hist = df_hist.dropna(subset=["Date"]).copy()

        league_name = league_meta.get("name", league_key)

        for _, fx in league_fixt.iterrows():
            home = str(fx["HomeTeam"])
            away = str(fx["AwayTeam"])

            lam_h, lam_a, lam_t = compute_lambdas(df_hist, home, away, window)

            p15 = prob_over_line(lam_t, 1.5)
            p25 = prob_over_line(lam_t, 2.5)

            odd15 = float(fx["Odd_Over15"]) if not pd.isna(fx["Odd_Over15"]) else 0.0
            odd25 = float(fx["Odd_Over25"]) if not pd.isna(fx["Odd_Over25"]) else 0.0

            pm15 = (1.0 / odd15) if odd15 > 1.0 else 0.0
            pm25 = (1.0 / odd25) if odd25 > 1.0 else 0.0

            edge15 = p15 - pm15
            edge25 = p25 - pm25

            k15 = kelly_fraction(p15, odd15)
            k25 = kelly_fraction(p25, odd25)

            base_row = {
                "Date": fx["Date"],
                "League": league_key,
                "LeagueName": league_name,
                "HomeTeam": home,
                "AwayTeam": away,
                "LambdaHome": lam_h,
                "LambdaAway": lam_a,
                "LambdaTotal": lam_t,
            }

            rows15.append(
                {
                    **base_row,
                    "Market": "O1.5",
                    "ProbModel": p15,
                    "Odd": odd15,
                    "ProbMarket": pm15,
                    "Edge": edge15,
                    "KellyTrue": k15,
                }
            )

            rows25.append(
                {
                    **base_row,
                    "Market": "O2.5",
                    "ProbModel": p25,
                    "Odd": odd25,
                    "ProbMarket": pm25,
                    "Edge": edge25,
                    "KellyTrue": k25,
                }
            )

    bankroll_cfg = cfg.get("bankroll", {})
    rules_cfg = cfg.get("rules", {})

    bankroll15 = float(bankroll_cfg.get("over15", 0.0))
    bankroll25 = float(bankroll_cfg.get("over25", 0.0))

    out15 = apply_market_rules(rows15, bankroll15, rules_cfg.get("over15", {}))
    out25 = apply_market_rules(rows25, bankroll25, rules_cfg.get("over25", {}))

    out15_path = BASE / "picks_over15.csv"
    out25_path = BASE / "picks_over25.csv"
    combo_path = BASE / "picks_hoje.csv"

    # Para abrir melhor no LibreOffice PT, usamos separador ";"
    out15.to_csv(out15_path, index=False, encoding="utf-8", sep=";")
    out25.to_csv(out25_path, index=False, encoding="utf-8", sep=";")
    combo = pd.concat([out15, out25], ignore_index=True)
    combo.to_csv(combo_path, index=False, encoding="utf-8", sep=";")

    print("OK. Gerados:")
    print(f"- {out15_path.name} ({len(out15)} picks)")
    print(f"- {out25_path.name} ({len(out25)} picks)")
    print(f"- {combo_path.name} ({len(combo)} picks)")

    # ==========================
    # Telegram (anti-duplicados por dia)
    # ==========================
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
    CHAT_ID = os.getenv("CHAT_ID", "").strip()

    if TELEGRAM_TOKEN and CHAT_ID:
        try:
            sent = load_sent_state(today_iso)

            new15 = []
            for r in df_to_rows(out15):
                pid = pick_id(r)
                if pid not in sent:
                    new15.append(r)

            new25 = []
            for r in df_to_rows(out25):
                pid = pick_id(r)
                if pid not in sent:
                    new25.append(r)

            msg_15 = build_message(new15, "PICKS OVER 1.5 (NOVAS)")
            if msg_15:
                _send_in_chunks(TELEGRAM_TOKEN, CHAT_ID, msg_15, "PICKS OVER 1.5")

            msg_25 = build_message(new25, "PICKS OVER 2.5 (NOVAS)")
            if msg_25:
                _send_in_chunks(TELEGRAM_TOKEN, CHAT_ID, msg_25, "PICKS OVER 2.5")

            for r in new15:
                sent.add(pick_id(r))
            for r in new25:
                sent.add(pick_id(r))

            save_sent_state(today_iso, sent)

            if msg_15 or msg_25:
                print(f"Telegram: enviei {len(new15)} novas O1.5 + {len(new25)} novas O2.5.")
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
    upload_csvs_to_github([out15_path, out25_path, combo_path], owner, repo, branch)


if __name__ == "__main__":
    main()
