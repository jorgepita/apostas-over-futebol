from urllib import parse, request

import pandas as pd


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
    max_len = 3900
    if not text:
        return
    if len(text) <= max_len:
        send_telegram_message(token, chat_id, text)
        return

    parts = []
    cur = ""
    for line in text.splitlines(True):
        if len(line) > max_len:
            if cur:
                parts.append(cur)
                cur = ""
            for i in range(0, len(line), max_len):
                parts.append(line[i:i + max_len])
            continue

        if len(cur) + len(line) > max_len:
            if cur:
                parts.append(cur)
            cur = line
        else:
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

    def _sort_key(r: dict):
        try:
            edge = float(r.get("Edge", 0.0) or 0.0)
        except Exception:
            edge = 0.0
        try:
            kelly = float(r.get("KellyTrue", 0.0) or 0.0)
        except Exception:
            kelly = 0.0
        try:
            prob = float(r.get("ProbModel", 0.0) or 0.0)
        except Exception:
            prob = 0.0
        try:
            odd = float(r.get("Odd", 0.0) or 0.0)
        except Exception:
            odd = 0.0
        return (
            str(r.get("Date", "")),
            -edge,
            -kelly,
            -prob,
            -odd,
            str(r.get("LeagueName", "")),
            str(r.get("HomeTeam", "")),
        )

    rows_sorted = sorted(rows, key=_sort_key)

    grouped = {}
    for r in rows_sorted:
        grouped.setdefault(str(r.get("Date", "")), []).append(r)

    msg = f"📊 {titulo}\n\n"

    for date_key in sorted(grouped.keys()):
        msg += f"📅 {date_key}\n"
        for r in grouped[date_key]:
            try:
                edge_txt = f"{float(r['Edge']):.2%}"
            except Exception:
                edge_txt = "—"
            try:
                stake_txt = f"{float(r.get('Stake€', 0.0)):.2f}€"
            except Exception:
                stake_txt = "0.00€"

            msg += (
                f"{r['LeagueName']} | {r['HomeTeam']} vs {r['AwayTeam']}\n"
                f"Market: {r['Market']} @ {r['Odd']}\n"
                f"Edge: {edge_txt} | Stake: {stake_txt}\n\n"
            )

    return msg.strip()
