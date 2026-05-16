from pathlib import Path
from datetime import datetime
import pandas as pd


def _safe_read_history(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()

    try:
        df = pd.read_csv(path, sep=';', dtype=str, encoding='utf-8').fillna('')
        return df
    except Exception:
        try:
            df = pd.read_csv(path, sep=',', dtype=str, encoding='utf-8').fillna('')
            return df
        except Exception:
            return pd.DataFrame()


def update_league_stats(history_path: Path | str, out_path: Path | str | None = None) -> None:
    hp = Path(history_path)
    outp = Path(out_path) if out_path is not None else hp.parent / 'league_stats.csv'

    df = _safe_read_history(hp)
    if df.empty:
        # write empty file with headers
        cols = [
            'League', 'Market', 'TotalPicks', 'Wins', 'Losses', 'Pending', 'WinRate%',
            'AvgOdds', 'TotalStake', 'TotalProfit', 'ROI%', 'Yield%', 'AvgEdge%', 'AvgKelly', 'LastUpdate'
        ]
        pd.DataFrame(columns=cols).to_csv(outp, index=False, sep=';', encoding='utf-8')
        print('[DBG] LEAGUE ROI SUMMARY (no history)')
        return

    # normalize possible column names
    if 'Liga' not in df.columns and 'League' in df.columns:
        df = df.rename(columns={'League': 'Liga'})
    if 'Mercado' not in df.columns and 'Market' in df.columns:
        df = df.rename(columns={'Market': 'Mercado'})

    # ensure columns exist
    for c in ['Liga', 'Mercado', 'Odd', 'Stake€', 'Lucro€', 'Edge%', 'Resultado', 'Kelly']:
        if c not in df.columns:
            df[c] = ''

    # convert numerics
    def to_float(col):
        return pd.to_numeric(df[col].replace('', pd.NA), errors='coerce').fillna(0.0)

    df['Odd_n'] = to_float('Odd')
    df['Stake_n'] = to_float('Stake€')
    df['Profit_n'] = to_float('Lucro€')
    df['Edge_n'] = to_float('Edge%')
    df['Kelly_n'] = to_float('Kelly') if 'Kelly' in df.columns else pd.Series([0.0]*len(df))

    # Pending: Resultado empty or not in W/L/P
    resolved_mask = df['Resultado'].isin(['W', 'L'])
    pending_mask = ~df['Resultado'].isin(['W', 'L', 'P'])

    groups = []
    for (league, market), g in df.groupby(['Liga', 'Mercado']):
        total = len(g)
        wins = int((g['Resultado'] == 'W').sum())
        losses = int((g['Resultado'] == 'L').sum())
        pending = int(pending_mask.loc[g.index].sum())

        resolved = g[resolved_mask.loc[g.index]]
        resolved_count = len(resolved)

        avg_odds = float(resolved['Odd_n'].mean()) if resolved_count > 0 else 0.0
        total_stake = float(resolved['Stake_n'].sum())
        total_profit = float(resolved['Profit_n'].sum())
        avg_edge = float(resolved['Edge_n'].mean()) if resolved_count > 0 else 0.0
        avg_kelly = float(g['Stake_n'].mean()) if len(g) > 0 else 0.0

        winrate = (wins / resolved_count * 100.0) if resolved_count > 0 else 0.0
        roi = (total_profit / total_stake * 100.0) if total_stake > 0 else 0.0
        # yield defined as average profit per resolved pick divided by average stake per resolved pick -> equals ROI
        yield_pct = roi

        groups.append({
            'League': league,
            'Market': market,
            'TotalPicks': int(total),
            'Wins': wins,
            'Losses': losses,
            'Pending': pending,
            'WinRate%': round(winrate, 2),
            'AvgOdds': round(avg_odds, 3),
            'TotalStake': round(total_stake, 2),
            'TotalProfit': round(total_profit, 2),
            'ROI%': round(roi, 2),
            'Yield%': round(yield_pct, 2),
            'AvgEdge%': round(avg_edge, 2),
            "AvgKelly": round(avg_kelly, 4),
            'LastUpdate': datetime.utcnow().isoformat() + 'Z',
        })

    out_df = pd.DataFrame(groups)
    if out_df.empty:
        out_df = pd.DataFrame(columns=[
            'League', 'Market', 'TotalPicks', 'Wins', 'Losses', 'Pending', 'WinRate%',
            'AvgOdds', 'TotalStake', 'TotalProfit', 'ROI%', 'Yield%', 'AvgEdge%', 'AvgKelly', 'LastUpdate'
        ])

 # sort by ROI desc
    out_df = out_df.sort_values(
        by=["ROI%", "WinRate%", "TotalPicks"],
        ascending=[False, False, False]
    ).reset_index(drop=True)

    def classify_tier(row):
        if row["TotalPicks"] < 3:
            return "Unproven"

        if row["ROI%"] >= 12:
            return "Elite"

        if row["ROI%"] >= 5:
            return "Strong"

        if row["ROI%"] >= 0:
            return "Neutral"

        return "Weak"

    out_df["Tier"] = out_df.apply(classify_tier, axis=1)

    out_df.to_csv(outp, index=False, sep=';', encoding='utf-8')

    # Console debug summary
    print('[DBG] LEAGUE ROI SUMMARY')

    for _, row in out_df.iterrows():
        try:
            league = str(row['League']).lower()
            market = str(row['Market'])
            roi_txt = f"{float(row['ROI%']):.1f}%"
            picks = int(row['TotalPicks'])
            tier = str(row['Tier'])

            print(
                f"[DBG] {league} | {market} | "
                f"ROI={roi_txt} | picks={picks} | tier={tier}"
            )

        except Exception:
            continue