# Football Bot

A personal football betting assistant. A Poisson model estimates goal-scoring rates for football matches and generates value bets on over/under goals (O1.5, O2.5, O3.5) and both-teams-to-score (BTTS) markets. The project manages a real bankroll with fractional Kelly staking, records all bets, settles results automatically, and displays everything in a web dashboard.

## Architecture

```
GitHub Actions (scheduled)
    └─ Python pipeline  →  picks_history.csv / picks_hoje_simplificado.csv  →  GitHub repo

Railway (always-on server)
    └─ Flask API (sync_server.py)
         ├─ GET  /load           ← reads cloud_state.json from GitHub
         ├─ POST /save           ← writes cloud_state.json to GitHub
         ├─ POST /run-settlement ← triggers the settlement engine
         └─ GET  /health, /

Browser (user)
    └─ index.html (single-file dashboard)
         ├─ fetches CSVs from GitHub raw URLs (bot picks)
         └─ fetches/saves cloud_state.json via Railway API (manual bets + dashboard state)
```

GitHub is the persistence layer for all data; Railway holds no local state. The frontend is a single self-contained HTML file with no build step.

## Repository Structure

```
/
├── index.html          ← The entire frontend dashboard
├── sync_server.py       ← Railway Flask API (the backend)
├── main.py / run_main.py / run_topup.py  ← Pick generation
├── update_results.py    ← Settlement engine
├── src/                 ← Python library modules (incl. league_registry.py)
├── docs/                ← Full project documentation — start here
├── tests/               ← Automated tests
├── tools/, archive/      ← One-off scripts and retired code
└── .github/workflows/    ← Scheduled GitHub Actions (bot.yml)
```

## Documentation

Full architecture, data flow, dashboard/backend reference, known issues, roadmap, and change log live under [`docs/`](docs/README.md). That documentation — not this file or conversation history — is the authoritative source of project knowledge.

## Working with an AI Assistant

[`CLAUDE.md`](CLAUDE.md) defines the required startup workflow for any Claude Code session working in this repository: read the docs in order before proposing or making changes.

## Getting Started

```
pip install -r requirements.txt
python main.py            # run the pick generation pipeline locally
python sync_server.py     # run the Railway API locally
```

Configuration lives in `config.json` (model parameters) and environment variables (API keys, credentials — see `docs/04_Backend.md`).

## License

No license is currently configured for this repository.
