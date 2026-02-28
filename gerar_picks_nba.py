# gerar_picks_nba.py
import base64
import json
import os
from pathlib import Path
from urllib import request, parse, error
from datetime import datetime, timedelta

import pandas as pd

BASE = Path(__file__).resolve().parent
SENT_STATE_PATH = BASE / "sent_state_nba.json"


# =============================
# Anti-duplicados (por dia)
# =============================
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
    SENT_STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_id(row: dict) -> str:
    return f"{row['Date']}|{row['League']}|{row['HomeTeam']}|{row['AwayTeam']}|{row['Market']}|{row['Line']}"


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


def build_message(rows: list[dict], titulo: str) -> str:
    if not rows:
        return ""
    msg = f"🏀 {titulo}\n\n"
    for r in rows:
        msg += (
            f"{r['HomeTeam']} vs {r['AwayTeam']}\n"
            f"Market: {r['Market']} {r['Line']} @ {r['Odd']}\n"
            f"ModelTotal: {r['ModelTotal']:.1f} | Edge: {r['Edge']:.2%} | Stake: {r.get('Stake€', 0.0):.2f}€\n\n"
        )
    return msg


# =============================
# Regras / stakes
# =============================
def kelly_fraction(p: float, odd: float) -> float:
    if odd is None or odd <= 1.0:
        return 0.0
    f = (p * odd - 1.0) / (odd - 1.0)
    return max(0.0, float(f))


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

    for col, dec in {"ModelTotal": 1, "ProbModel": 3, "ProbMarket": 3, "Edge": 4, "KellyTrue": 4, "Stake€": 2}.items():
        if col in df.columns:
            df[col] = df[col].round(dec)

    return df


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

    payload = {"message": message, "content": base64.b64encode(content_bytes).decode("utf-8"), "branch": branch}
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
            msg = f"Update {fp.name} ({datetime.utcnow().isoformat()}Z)"
            github_put_file(owner, repo, rel_path, content, branch, token, msg)
            ok += 1
        except Exception as e:
            print(f"GitHub: falhou upload de {fp.name} -> {e}")

    print(f"GitHub: upload concluído ({ok}/{len(files)} ficheiros).")


# =============================
# Modelo NBA simples
# =============================
def normal_cdf(x: float) -> float:
    # CDF Normal(0,1)
    import math
    return 0.5 * (1.0 + math.erf(x / (2**0.5)))


def main():
    cfg_path = BASE / "config.json"
    if not cfg_path.exists():
        raise SystemExit("Falta config.json na pasta do projeto.")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    fixtures_path = BASE / "fixtures_today_nba.csv"
    if not fixtures_path.exists():
        raise SystemExit("Falta fixtures_today_nba.csv na pasta do projeto.")

    fixtures = pd.read_csv(fixtures_path, sep=None, engine="python")

    required = {"Date", "League", "HomeTeam", "AwayTeam", "TotalLine", "Odd_Over"}
    if not required.issubset(set(fixtures.columns)):
        raise SystemExit(f"fixtures_today_nba.csv precisa das colunas: {sorted(required)}")

    fixtures["Date"] = pd.to_datetime(fixtures["Date"], errors="coerce").dt.date
    fixtures = fixtures.dropna(subset=["Date"]).copy()

    try:
        from zoneinfo import ZoneInfo
        now_pt = datetime.now(ZoneInfo("Europe/Lisbon"))
    except Exception:
        now_pt = datetime.utcnow()

    days_ahead = int(cfg.get("run", {}).get("days_ahead", 1))
    start = now_pt.date()
    end = start + timedelta(days=days_ahead)
    today_iso = start.isoformat()

    fixtures = fixtures[(fixtures["Date"] >= start) & (fixtures["Date"] <= end)].copy()
    fixtures["Date"] = fixtures["Date"].astype(str)

    # histórico
    hist_path = BASE / "data_raw" / "nba.csv"
    if not hist_path.exists():
        raise SystemExit("Falta data_raw/nba.csv (histórico NBA).")

    df_hist = pd.read_csv(hist_path, sep=None, engine="python")

    need = {"Date", "HomeTeam", "AwayTeam", "HomePts", "AwayPts"}
    if not need.issubset(set(df_hist.columns)):
        raise SystemExit(f"nba.csv precisa colunas: {sorted(need)}")

    df_hist["Date"] = pd.to_datetime(df_hist["Date"], errors="coerce")
    df_hist = df_hist.dropna(subset=["Date"]).copy()

    # config NBA
    nba_cfg = cfg.get("nba", {})
    window = int(nba_cfg.get("window", 10))
    sigma = float(nba_cfg.get("sigma_total", 14.0))  # desvio típico total pontos (ajustável)

    bankroll = float(cfg.get("bankroll", {}).get("nba_over", 0.0))
    rules = cfg.get("rules", {}).get("nba_over", {"edge_min": 0.0, "kelly_fraction": 0.25, "cap_frac": 0.05, "daily_cap_frac": 0.15, "min_picks": 1})

    rows = []

    def team_last_n(team: str) -> pd.DataFrame:
        # junta jogos onde a equipa é home ou away, normaliza pontos_for/against
        h = df_hist[df_hist["HomeTeam"] == team][["Date", "HomePts", "AwayPts"]].copy()
        h["PF"] = pd.to_numeric(h["HomePts"], errors="coerce")
        h["PA"] = pd.to_numeric(h["AwayPts"], errors="coerce")

        a = df_hist[df_hist["AwayTeam"] == team][["Date", "HomePts", "AwayPts"]].copy()
        a["PF"] = pd.to_numeric(a["AwayPts"], errors="coerce")
        a["PA"] = pd.to_numeric(a["HomePts"], errors="coerce")

        d = pd.concat([h[["Date", "PF", "PA"]], a[["Date", "PF", "PA"]]], ignore_index=True)
        d = d.dropna(subset=["PF", "PA", "Date"]).sort_values("Date")
        return d.tail(window)

    for _, fx in fixtures.iterrows():
        home = str(fx["HomeTeam"])
        away = str(fx["AwayTeam"])
        line = float(fx["TotalLine"])
        odd_over = float(fx["Odd_Over"]) if not pd.isna(fx["Odd_Over"]) else 0.0
        if odd_over <= 1.0:
            continue

        h_last = team_last_n(home)
        a_last = team_last_n(away)
        if len(h_last) < max(3, window // 2) or len(a_last) < max(3, window // 2):
            continue

        # estimativas simples
        home_off = float(h_last["PF"].mean())
        home_def = float(h_last["PA"].mean())
        away_off = float(a_last["PF"].mean())
        away_def = float(a_last["PA"].mean())

        # total previsto: média cruzada (ofensa vs defesa)
        home_exp = 0.5 * home_off + 0.5 * away_def
        away_exp = 0.5 * away_off + 0.5 * home_def
        model_total = float(home_exp + away_exp)

        # p(Over) assumindo Normal(model_total, sigma)
        # P(T > line) = 1 - CDF((line - mu)/sigma)
        z = (line - model_total) / max(1e-6, sigma)
        p_over = 1.0 - normal_cdf(z)

        pm_over = 1.0 / odd_over
        edge = p_over - pm_over
        k = kelly_fraction(p_over, odd_over)

        rows.append(
            {
                "Date": fx["Date"],
                "League": "nba",
                "HomeTeam": home,
                "AwayTeam": away,
                "Market": "OVER",
                "Line": line,
                "Odd": odd_over,
                "ModelTotal": model_total,
                "ProbModel": p_over,
                "ProbMarket": pm_over,
                "Edge": edge,
                "KellyTrue": k,
            }
        )

    # debug rápido
    if rows:
        df_dbg = pd.DataFrame(rows)
        print(f"[DBG] PRE-FILTER NBA: rows={len(df_dbg)} edge_max={df_dbg['Edge'].max():.4f} edge_min={df_dbg['Edge'].min():.4f} odd_min={df_dbg['Odd'].min():.2f} odd_max={df_dbg['Odd'].max():.2f}")
    else:
        print("[DBG] PRE-FILTER NBA: rows=0")

    out = apply_market_rules(rows, bankroll, rules)

    out_path = BASE / "picks_nba_over.csv"
    out.to_csv(out_path, index=False, encoding="utf-8", sep=";")

    print("OK. Gerados:")
    print(f"- {out_path.name} ({len(out)} picks)")

    # Telegram (anti-duplicados)
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
    CHAT_ID = os.getenv("CHAT_ID", "").strip()
    if TELEGRAM_TOKEN and CHAT_ID:
        try:
            sent = load_sent_state(today_iso)

            new_rows = []
            for r in out.to_dict(orient="records") if len(out) else []:
                pid = pick_id(r)
                if pid not in sent:
                    new_rows.append(r)

            msg = build_message(new_rows, "PICKS NBA OVER (NOVAS)")
            if msg:
                _send_in_chunks(TELEGRAM_TOKEN, CHAT_ID, msg, "PICKS NBA OVER")
                for r in new_rows:
                    sent.add(pick_id(r))
                save_sent_state(today_iso, sent)
                print(f"Telegram: enviei {len(new_rows)} novas NBA.")
            else:
                print("Telegram: sem novas picks NBA (não enviei).")
        except Exception as e:
            print(f"Telegram: erro ao enviar NBA -> {e}")
    else:
        print("Telegram: TOKEN ou CHAT_ID em falta (NBA não enviei).")

    # GitHub upload
    owner = "jorgepita"
    repo = "apostas-over-futebol"
    branch = "main"
    upload_csvs_to_github([out_path], owner, repo, branch)


if __name__ == "__main__":
    main()
