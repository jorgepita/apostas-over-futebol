# gerar_picks.py  (NBA - apenas OVER, window=15)
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
    # ID único por jogo/linha
    return (
        f"{row.get('Date','')}|{row.get('League','')}|{row.get('HomeTeam','')}|"
        f"{row.get('AwayTeam','')}|OVER|{row.get('Line','')}"
    )


# =============================
# Helpers estatísticos
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


def safe_std(series) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 2:
        return 0.0
    return float(s.std(ddof=1))


def normal_cdf(x: float, mu: float, sigma: float) -> float:
    # CDF Normal via erf
    if sigma <= 1e-9:
        return 1.0 if x >= mu else 0.0
    z = (x - mu) / (sigma * math.sqrt(2.0))
    return 0.5 * (1.0 + math.erf(z))


def prob_over_total(mu_total: float, sigma_total: float, line: float) -> float:
    # P(Total > line) = 1 - CDF(line)
    return 1.0 - normal_cdf(line, mu_total, sigma_total)


def kelly_fraction(p: float, odd: float) -> float:
    if odd is None or odd <= 1.0:
        return 0.0
    f = (p * odd - 1.0) / (odd - 1.0)
    return max(0.0, float(f))


# =============================
# Modelo NBA (muito simples e robusto)
# - Estima pontos esperados de cada equipa usando:
#   ataque (pontos marcados) e defesa (pontos sofridos)
#   em janelas recentes "window".
# - Desvio padrão do total estimado pelo histórico recente de totais.
# =============================
def build_team_history(df_hist: pd.DataFrame) -> pd.DataFrame:
    """
    Converte jogos Home/Away em linhas por equipa:
    Date, Team, PTS, PA
    """
    home = df_hist[["Date", "HomeTeam", "FTHG", "FTAG"]].copy()
    home.columns = ["Date", "Team", "PTS", "PA"]

    away = df_hist[["Date", "AwayTeam", "FTAG", "FTHG"]].copy()
    away.columns = ["Date", "Team", "PTS", "PA"]

    out = pd.concat([home, away], ignore_index=True)
    out["PTS"] = pd.to_numeric(out["PTS"], errors="coerce")
    out["PA"] = pd.to_numeric(out["PA"], errors="coerce")
    out = out.dropna(subset=["Date", "Team", "PTS", "PA"]).copy()
    return out


def last_n_team(team_df: pd.DataFrame, team: str, n: int) -> pd.DataFrame:
    d = team_df[team_df["Team"] == team].sort_values("Date")
    return d.tail(n)


def expected_points(team_df: pd.DataFrame, team: str, opp: str, window: int) -> tuple[float, float]:
    """
    Retorna (mu_team, mu_opp_component):
      mu_team: pontos esperados do 'team'
      mu_opp_component: pontos sofridos esperados pelo 'opp' (defesa do opp)
    """
    t_last = last_n_team(team_df, team, window)
    o_last = last_n_team(team_df, opp, window)

    mu_scored = safe_mean(t_last["PTS"]) if len(t_last) else 0.0
    mu_allowed_by_opp = safe_mean(o_last["PA"]) if len(o_last) else 0.0

    return mu_scored, mu_allowed_by_opp


def estimate_total(df_hist: pd.DataFrame, home: str, away: str, window: int) -> tuple[float, float, float, float]:
    """
    Devolve:
      mu_home, mu_away, mu_total, sigma_total
    """
    team_df = build_team_history(df_hist)

    # fallback liga (se equipa não tiver histórico suficiente)
    league_mu_pts = safe_mean(team_df["PTS"])
    if league_mu_pts <= 0:
        league_mu_pts = 110.0  # NBA típico

    # médias por equipa
    h_scored, a_allowed = expected_points(team_df, home, away, window)
    a_scored, h_allowed = expected_points(team_df, away, home, window)

    # se faltar histórico, usa média liga
    if h_scored <= 0:
        h_scored = league_mu_pts
    if a_scored <= 0:
        a_scored = league_mu_pts
    if a_allowed <= 0:
        a_allowed = league_mu_pts
    if h_allowed <= 0:
        h_allowed = league_mu_pts

    # mistura ataque vs defesa (simples e estável)
    mu_home = 0.5 * h_scored + 0.5 * a_allowed
    mu_away = 0.5 * a_scored + 0.5 * h_allowed
    mu_total = mu_home + mu_away

    # sigma do total pelos totais recentes dos jogos dessas equipas
    df_hist = df_hist.sort_values("Date").copy()
    df_hist["TOTAL"] = pd.to_numeric(df_hist["FTHG"], errors="coerce") + pd.to_numeric(df_hist["FTAG"], errors="coerce")

    # jogos onde home ou away participa
    mask = (df_hist["HomeTeam"].isin([home, away])) | (df_hist["AwayTeam"].isin([home, away]))
    recent_totals = df_hist.loc[mask, "TOTAL"].tail(max(30, window * 2))
    sigma_total = safe_std(recent_totals)
    if sigma_total <= 1e-6:
        # fallback: sigma típico NBA
        sigma_total = 14.0

    return float(mu_home), float(mu_away), float(mu_total), float(sigma_total)


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
            f"{r['HomeTeam']} vs {r['AwayTeam']} | Line: {r['Line']} | Over @ {r['Odd']}\n"
            f"Model P: {float(r['ProbModel']):.3f} | Market P: {float(r['ProbMarket']):.3f}\n"
            f"Edge: {float(r['Edge']):.2%} | Stake: {float(r.get('Stake€', 0.0)):.2f}€\n\n"
        )
    return msg


# =============================
# Regras / stakes
# =============================
def apply_rules(rows: list[dict], bankroll: float, rules: dict) -> pd.DataFrame:
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
        "MuHome": 2,
        "MuAway": 2,
        "MuTotal": 2,
        "SigmaTotal": 2,
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
            msg = f"Update {fp.name} ({datetime.now(timezone.utc).isoformat()}Z)"
            github_put_file(owner, repo, rel_path, content, branch, token, msg)
            ok += 1
        except Exception as e:
            print(f"GitHub: falhou upload de {fp.name} -> {e}")

    print(f"GitHub: upload concluído ({ok}/{len(files)} ficheiros).")


# =============================
# Main
# =============================
def main():
    # ---- Config (se não existir, usa defaults seguros) ----
    cfg_path = BASE / "config.json"
    cfg = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise SystemExit(f"config.json inválido: {e}")

    run_cfg = cfg.get("run", {})
    history_cfg = cfg.get("history", {})
    rules_cfg = cfg.get("rules", {})
    bankroll_cfg = cfg.get("bankroll", {})

    # window pedido: 15
    window = int(history_cfg.get("window", 15))
    days_ahead = int(run_cfg.get("days_ahead", 1))

    # ---- Fixtures do dia (NBA) ----
    fixtures_path = BASE / "fixtures_today.csv"
    if not fixtures_path.exists():
        raise SystemExit("Falta fixtures_today.csv (o fetch NBA tem de correr antes).")

    fixtures = pd.read_csv(fixtures_path, sep=None, engine="python")

    # Mapeia colunas possíveis
    col_map = {
        "Date": ["Date", "date", "game_date", "CommenceDate"],
        "League": ["League", "league", "sport", "competition"],
        "HomeTeam": ["HomeTeam", "home", "home_team", "Home"],
        "AwayTeam": ["AwayTeam", "away", "away_team", "Away"],
        "Line": ["Line", "line", "TotalLine", "total_line", "Point", "point"],
        "Odd_Over": ["Odd_Over", "odd_over", "OverOdd", "over_odds", "price_over", "OddOver"],
    }

    def pick_col(df: pd.DataFrame, key: str) -> str | None:
        for c in col_map.get(key, []):
            if c in df.columns:
                return c
        return None

    c_date = pick_col(fixtures, "Date")
    c_league = pick_col(fixtures, "League")
    c_home = pick_col(fixtures, "HomeTeam")
    c_away = pick_col(fixtures, "AwayTeam")
    c_line = pick_col(fixtures, "Line")
    c_odd = pick_col(fixtures, "Odd_Over")

    missing = [k for k, c in [("Date", c_date), ("League", c_league), ("HomeTeam", c_home), ("AwayTeam", c_away), ("Line", c_line), ("Odd_Over", c_odd)] if c is None]
    if missing:
        raise SystemExit(f"fixtures_today.csv NBA precisa colunas (ou equivalentes): {missing}. Colunas atuais: {list(fixtures.columns)}")

    fixtures = fixtures.rename(columns={c_date: "Date", c_league: "League", c_home: "HomeTeam", c_away: "AwayTeam", c_line: "Line", c_odd: "Odd_Over"}).copy()

    # Só NBA
    fixtures["League"] = fixtures["League"].astype(str).str.lower()
    fixtures = fixtures[fixtures["League"].isin(["nba", "basketball_nba"])].copy()

    if fixtures.empty:
        raise SystemExit("fixtures_today.csv não tem jogos NBA (League=nba).")

    # Date -> date (assume ISO)
    fixtures["Date"] = pd.to_datetime(fixtures["Date"], errors="coerce").dt.date
    fixtures = fixtures.dropna(subset=["Date"]).copy()

    # Janela de dias
    today = datetime.now(timezone.utc).date()
    end = today + timedelta(days=days_ahead)
    today_iso = today.isoformat()

    fixtures = fixtures[(fixtures["Date"] >= today) & (fixtures["Date"] <= end)].copy()
    fixtures["Date"] = fixtures["Date"].astype(str)

    print("[DBG] GERAR_PICKS NBA START")
    print(f"[DBG] fixtures NBA in range: {len(fixtures)} | window={window} | days_ahead={days_ahead}")

    # ---- Histórico NBA ----
    hist_path = BASE / "data_raw" / "nba.csv"
    if not hist_path.exists():
        raise SystemExit("Falta data_raw/nba.csv (histórico).")

    df_hist = pd.read_csv(hist_path, sep=None, engine="python")
    need_hist = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    if not need_hist.issubset(set(df_hist.columns)):
        raise SystemExit(f"nba.csv precisa colunas {sorted(need_hist)}. Tem: {list(df_hist.columns)}")

    df_hist["Date"] = pd.to_datetime(df_hist["Date"], errors="coerce")
    df_hist = df_hist.dropna(subset=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]).copy()

    # ---- Gerar rows (apenas OVER) ----
    rows = []
    for _, fx in fixtures.iterrows():
        home = str(fx["HomeTeam"]).strip()
        away = str(fx["AwayTeam"]).strip()

        try:
            line = float(fx["Line"])
        except Exception:
            continue

        try:
            odd_over = float(fx["Odd_Over"])
        except Exception:
            continue

        if odd_over <= 1.0:
            continue

        mu_h, mu_a, mu_t, sig_t = estimate_total(df_hist, home, away, window)

        # Ajuste opcional
        mu_boost = float(history_cfg.get("mu_boost", 1.0))
        if mu_boost and mu_boost != 1.0:
            mu_h *= mu_boost
            mu_a *= mu_boost
            mu_t = mu_h + mu_a

        p_model = prob_over_total(mu_t, sig_t, line)
        p_market = (1.0 / odd_over) if odd_over > 1.0 else 0.0
        edge = p_model - p_market
        k = kelly_fraction(p_model, odd_over)

        rows.append(
            {
                "Date": fx["Date"],
                "League": "nba",
                "HomeTeam": home,
                "AwayTeam": away,
                "Line": line,
                "Odd": odd_over,
                "MuHome": mu_h,
                "MuAway": mu_a,
                "MuTotal": mu_t,
                "SigmaTotal": sig_t,
                "ProbModel": p_model,
                "ProbMarket": p_market,
                "Edge": edge,
                "KellyTrue": k,
            }
        )

    # debug curto
    if rows:
        edges = [r["Edge"] for r in rows]
        odds = [r["Odd"] for r in rows]
        print(f"[DBG] PRE-FILTER rows={len(rows)} edge_max={max(edges):.4f} edge_min={min(edges):.4f} odd_min={min(odds):.2f} odd_max={max(odds):.2f}")
    else:
        print("[DBG] PRE-FILTER rows=0")

    bankroll = float(bankroll_cfg.get("nba_over", bankroll_cfg.get("over", 0.0)))
    out = apply_rules(rows, bankroll, rules_cfg.get("nba_over", rules_cfg.get("over", {})))

    out_path = BASE / "picks_nba_over.csv"
    combo_path = BASE / "picks_hoje.csv"

    # separador ; para LibreOffice PT
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
                _send_in_chunks(TELEGRAM_TOKEN, CHAT_ID, msg, "PICKS NBA OVER")
                for r in new_rows:
                    sent.add(pick_id(r))
                save_sent_state(today_iso, sent)
                print(f"Telegram: enviei {len(new_rows)} novas NBA OVER.")
            else:
                print("Telegram: sem novas picks (não enviei).")
        except Exception as e:
            print(f"Telegram: erro ao enviar -> {e}")
    else:
        print("Telegram: TOKEN ou CHAT_ID em falta (não enviei mensagem).")

    # ==========================
    # GitHub upload dos CSVs gerados
    # ==========================
    owner = "jorgepita"
    repo = "apostas-over-futebol"
    branch = "main"
    upload_csvs_to_github([out_path, combo_path], owner, repo, branch)


if __name__ == "__main__":
    main()
