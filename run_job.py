import os
import subprocess
import sys
import traceback
from urllib import request, parse


def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    if not token or not chat_id or not text:
        return
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


def run(cmd: list[str]) -> None:
    print(">>", " ".join(cmd))
    r = subprocess.run(cmd, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {r.returncode}: {' '.join(cmd)}")


def main():
    # Se estas vars não existirem, falha logo (melhor do que correr e dar 401/404)
    required_env = ["ODDS_API_KEY", "TELEGRAM_TOKEN", "CHAT_ID"]
    missing = [k for k in required_env if not os.getenv(k, "").strip()]
    if missing:
        raise SystemExit(f"Missing environment variables: {', '.join(missing)}")

    run([sys.executable, "fetch_oddsapi_fixtures.py"])
    run([sys.executable, "gerar_picks.py"])


if __name__ == "__main__":
    try:
        main()
        print("JOB OK ✅")
    except Exception as e:
        # alerta no Telegram
        token = os.getenv("TELEGRAM_TOKEN", "").strip()
        chat_id = os.getenv("CHAT_ID", "").strip()

        err = "".join(traceback.format_exception_only(type(e), e)).strip()
        msg = f"⚠️ apostas-over-futebol FALHOU\n{err}"
        try:
            send_telegram_message(token, chat_id, msg)
        except Exception:
            pass

        # log e marcar run como failed no Render
        print("JOB FAILED ❌")
        traceback.print_exc()
        sys.exit(1)