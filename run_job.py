import subprocess
import sys

def run(cmd: list[str]):
    print(">>", " ".join(cmd))
    r = subprocess.run(cmd, text=True)
    if r.returncode != 0:
        sys.exit(r.returncode)

def main():
    run([sys.executable, "fetch_oddsapi_fixtures.py"])
    run([sys.executable, "gerar_picks.py"])

if __name__ == "__main__":
    main()