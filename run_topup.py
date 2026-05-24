import sys
import subprocess


def run(cmd):
    print(">>", " ".join(cmd), flush=True)
    p = subprocess.run(cmd, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {p.returncode}: {' '.join(cmd)}")


if __name__ == "__main__":
    py = sys.executable
    print("[TOPUP] A buscar fixtures actualizadas (ligas de odds tardias)...")
    run([py, "fetch_oddsapi_fixtures.py"])
    print("[TOPUP] A iniciar geração top-up (apenas ligas não-EU)...")
    from main import main
    main(topup_mode=True)
