import pandas as pd

FILE = "picks_hoje_simplificado.csv"

df = pd.read_csv(FILE, sep=";")

for i,row in df.iterrows():

    if pd.notna(row["Resultado"]):
        continue

    # exemplo simples (placeholder)
    # aqui depois ligamos API resultados

    resultado = ""

    if resultado == "win":
        lucro = row["Stake€"] * (row["Odd"] - 1)

    elif resultado == "lose":
        lucro = -row["Stake€"]

    else:
        lucro = 0

    df.at[i,"Resultado"] = resultado
    df.at[i,"Lucro€"] = round(lucro,2)

df.to_csv(FILE,index=False,sep=";")

print("Resultados atualizados")
