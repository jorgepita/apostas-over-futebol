# run_job.py
import sys
import subprocess


def run(cmd):
    print(">>", " ".join(cmd), flush=True)
    p = subprocess.run(cmd, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {p.returncode}: {' '.join(cmd)}")


def main():
    py = sys.executable

    # ===== FUTEBOL =====
    run([py, "fetch_oddsapi_fixtures.py"])
    run([py, "gerar_picks.py"])

    # ===== NBA =====
    run([py, "fetch_oddsapi_fixtures_nba.py"])
    run([py, "gerar_picks_nba.py"])


if __name__ == "__main__":
    main()
