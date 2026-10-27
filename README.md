# AI Capital Lab

A mobile-friendly AI-team workspace with a static GitHub Pages frontend and an optional secure backend for real model calls.

## Current features
- Coordinator, Analyst, Developer and Independent Reviewer roles.
- Task board, completion state, browser-local persistence and activity log.
- Exportable team report.
- Frontend can connect to a separately hosted backend through the Backend-URL field.
- When no backend is configured, the app clearly labels the workflow as a local template. A failed model call is shown as a failure, not disguised as an AI result.

## Frontend
The static site is published from the repository root using GitHub Pages. It can be opened at:
https://gurraslut-design.github.io/AI-CAPITAL-2.0/

## Secure AI backend
The `backend/` directory contains a Node.js/Express service with:
- `GET /api/health` to report whether a model is configured.
- `POST /api/team-run` to run Coordinator → Analyst → Developer → Independent Reviewer → Coordinator through server-side OpenAI Responses API calls.
- CORS allow-list configuration.
- No exchange integration and no trading/order endpoints.

### Required server environment variables
- `OPENAI_API_KEY`: provider key stored only in the backend host's secret manager.
- `OPENAI_MODEL`: a model ID enabled for that provider key.
- `ALLOWED_ORIGINS`: comma-separated allowed browser origins; include `https://gurraslut-design.github.io`.
- `PORT` is optional and supplied by many hosts.

Never put provider API keys in `index.html`, `app.js`, local storage, or any public repository. The backend must be deployed to a server that supports Node.js before real AI calls work. In the frontend, enter that server's base URL and tap **Testa anslutning**. GitHub Pages itself is static and cannot run the backend.

## Safety
This app does not connect to exchanges or place trades. Bitcoin functionality must remain paper/backtest-only. AI outputs are suggestions, not verified facts or actions; check important claims before relying on them.
