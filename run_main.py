import sys
import subprocess


def run(cmd):
    print(">>", " ".join(cmd), flush=True)
    p = subprocess.run(cmd, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {p.returncode}: {' '.join(cmd)}")


def main():
    py = sys.executable
    print("[MAIN_RUN] A buscar fixtures actualizadas...")
    run([py, "fetch_oddsapi_fixtures.py"])
    print("[MAIN_RUN] A gerar picks principais (pipeline completo)...")
    run([py, "main.py"])


if __name__ == "__main__":
    main()
