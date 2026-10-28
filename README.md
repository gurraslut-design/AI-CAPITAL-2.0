# AI Capital Lab

A mobile-friendly AI-team workspace with a static GitHub Pages frontend and an optional secure backend for real model calls.

## Current features
- Coordinator, Analyst, Developer and Independent Reviewer roles.
- Task board, completion state, browser-local persistence and activity log.
- Exportable team report.
- The frontend can connect to a separately hosted backend through the Backend-URL field.
- Without a backend, the workflow is clearly labelled as a local template. Failed model calls are shown as failures, not disguised as AI results.
- A separate Python trading research script supports historical backtesting and a Kraken public-market-data paper signal. It cannot place orders.

## Frontend
The static site is published from the repository root using GitHub Pages:
https://gurraslut-design.github.io/AI-CAPITAL-2.0/

## Trading research (paper/backtest only)
Requires Python 3.9+ and no third-party packages. Download a historical OHLCV CSV with columns `time` (optional), `open`, `high`, `low`, `close` and optionally `volume`.

Run a historical simulation:
```bash
python trading_bot.py BACKTEST --csv path/to/candles.csv --balance 1000
```

Read the latest Kraken public 5-minute candles and print a paper signal:
```bash
python trading_bot.py PAPER
```

Strategy: long-only EMA20/EMA50 bullish crossover with RSI14 above 50; 1% stop loss; 2% take profit; 1% balance risk; one position at a time. Backtests enter at the next candle's open after a completed-candle signal and conservatively assume stop-loss first if a candle touches both stop and target. Kraken's public OHLC endpoint only supplies recent candles; use an archive CSV for longer historical tests.

The default fee assumption is **0.8% per side**, configurable with `--fee` (for example `--fee 0.002` for 0.2%). Confirm your actual Kraken fee tier before trusting results; fees can overwhelm a small-account strategy. The script uses public market data only, stores no persistent positions, has no exchange API credentials, and has no order-placement code. PAPER output is a signal snapshot, not a continuously running trading service.

## Backend
The `backend/` directory contains a Node.js/Express service with:
- `GET /api/health` to report readiness.
- `POST /api/team-run` to run Coordinator → Analyst → Developer → Independent Reviewer → Coordinator through server-side OpenAI Responses API calls.
- CORS origin allow-list.
- No exchange integration and no trading/order endpoints.

### Deploy backend with Render
The repository includes `render.yaml` for a Render web service. To deploy it, sign in to Render and create a new Blueprint from this public GitHub repository. Render will read the configuration and request the required environment variables. The backend can then be connected in the app using its HTTPS service URL.

Required server environment variables:
- `OPENAI_API_KEY`: provider key stored only in the backend host's secret manager.
- `OPENAI_MODEL`: a model ID enabled for that provider key.
- `ALLOWED_ORIGINS`: optional comma-separated allowed browser origins; default is `https://gurraslut-design.github.io`.
- `PORT` is supplied by Render.

Never put provider API keys in `index.html`, `app.js`, local storage, or any public repository. The backend host must be running before real AI calls work. In the frontend, enter the backend HTTPS URL and tap **Testa anslutning**. GitHub Pages itself is static and cannot run the backend.

## Safety
This app does not connect to exchanges or place trades. Bitcoin functionality remains paper/backtest-only. AI outputs are suggestions, not verified facts or actions; check important claims before relying on them. Do not deposit funds or enable real trading based on a backtest alone.
