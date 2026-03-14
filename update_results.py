import pandas as pd

FILE = "picks_hoje_simplificado.csv"

# ler tudo como texto
df = pd.read_csv(FILE, sep=";", dtype=str).fillna("")

# garantir colunas
if "Resultado" not in df.columns:
    df["Resultado"] = ""

if "Lucro€" not in df.columns:
    df["Lucro€"] = ""

if "Stake€" not in df.columns:
    df["Stake€"] = ""

if "Odd" not in df.columns:
    df["Odd"] = ""

for i, row in df.iterrows():
    resultado_atual = str(row.get("Resultado", "")).strip()

    # se já tiver resultado, ignora
    if resultado_atual not in ["", "nan", "None"]:
        continue

    # placeholder por agora
    resultado = ""

    try:
        stake = float(str(row.get("Stake€", "")).replace(",", "."))
    except Exception:
        stake = 0.0

    try:
        odd = float(str(row.get("Odd", "")).replace(",", "."))
    except Exception:
        odd = 0.0

    if resultado == "win":
        lucro = round(stake * (odd - 1), 2)
    elif resultado == "lose":
        lucro = round(-stake, 2)
    else:
        lucro = 0.0

    df.at[i, "Resultado"] = resultado
    df.at[i, "Lucro€"] = str(lucro)

df.to_csv(FILE, index=False, sep=";")

print("Resultados atualizados")
