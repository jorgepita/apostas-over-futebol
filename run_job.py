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
    run([py, "update_results.py"])


if __name__ == "__main__":
    main()
