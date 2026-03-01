import subprocess
import sys

def run(script):
    print(f"\n>>> Running {script}")
    result = subprocess.run([sys.executable, script])
    if result.returncode != 0:
        raise SystemExit(f"Erro ao correr {script}")

def main():
    run("fetch_fixtures_nba.py")
    run("gerar_picks_nba.py")

if __name__ == "__main__":
    main()
