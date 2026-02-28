from pathlib import Path
import pandas as pd

# Caminho para o ficheiro grande (ajusta se preciso)
SRC = Path("C:/Users/jjpit/Downloads/NBA_BoxScore_1949-2021/data/1949-2020_officialBoxScore.csv")

OUT = Path("nba_small.csv")

print("A ler ficheiro grande...")
df = pd.read_csv(SRC)

print("Colunas disponíveis:")
print(df.columns.tolist())

# Ajusta nomes conforme dataset (vamos ver depois)
df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")

# Ficar só com jogos desde 2010
df = df[df["GAME_DATE"].dt.year >= 2010]

# Criar formato simples
out = pd.DataFrame({
    "Date": df["GAME_DATE"],
    "HomeTeam": df["HOME_TEAM_NAME"],
    "AwayTeam": df["VISITOR_TEAM_NAME"],
    "HomePts": df["HOME_TEAM_SCORE"],
    "AwayPts": df["VISITOR_TEAM_SCORE"]
})

out = out.dropna()

out.to_csv(OUT, index=False)
print("Criado nba_small.csv")
print("Tamanho:", OUT.stat().st_size / (1024*1024), "MB")
