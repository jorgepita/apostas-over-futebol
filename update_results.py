import pandas as pd

FILE = "picks_hoje_simplificado.csv"

df = pd.read_csv(FILE, sep=";")

# garantir que as colunas existem
if "Resultado" not in df.columns:
    df["Resultado"] = ""

if "Lucro€" not in df.columns:
    df["Lucro€"] = 0.0

# converter para tipos corretos
df["Resultado"] = df["Resultado"].astype(str)
df["Lucro€"] = pd.to_numeric(df["Lucro€"], errors="coerce").fillna(0)

for i, row in df.iterrows():

    # se já tiver resultado, ignora
    if row["Resultado"] not in ["", "nan"]:
        continue

    # placeholder (mais tarde ligamos API resultados)
    resultado = ""

    if resultado == "win":
        lucro = row["Stake€"] * (row["Odd"] - 1)

    elif resultado == "lose":
        lucro = -row["Stake€"]

    else:
        lucro = 0

    df.at[i, "Resultado"] = resultado
    df.at[i, "Lucro€"] = round(lucro, 2)

df.to_csv(FILE, index=False, sep=";")

print("Resultados atualizados")
