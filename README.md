# AI Capital Lab

A mobile-friendly AI-team workspace with a static GitHub Pages frontend and an optional secure backend for real model calls.

## Current features
- Coordinator, Analyst, Developer and Independent Reviewer roles.
- Task board, completion state, browser-local persistence and activity log.
- Exportable team report.
- The frontend can connect to a separately hosted backend through the Backend-URL field.
- Without a backend, the workflow is clearly labelled as a local template. Failed model calls are shown as failures, not disguised as AI results.

## Frontend
The static site is published from the repository root using GitHub Pages:
https://gurraslut-design.github.io/AI-CAPITAL-2.0/

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
This app does not connect to exchanges or place trades. Bitcoin functionality must remain paper/backtest-only. AI outputs are suggestions, not verified facts or actions; check important claims before relying on them.
