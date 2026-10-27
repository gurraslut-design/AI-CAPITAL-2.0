# AI Capital Lab

A mobile-friendly static prototype for coordinating a small AI team.

## Current features
- Coordinator, Analyst, Developer and Independent Reviewer role cards.
- Task board with completion state and local browser persistence.
- Activity log, structured workflow report and text export.
- Clear distinction between template-based workflow and real AI model calls.

## Run
Open `index.html` in a modern browser or serve this directory with any static web server.

## Publish with GitHub Pages
In repository Settings → Pages, select **GitHub Actions** as the deployment source. The workflow will deploy the static app on pushes to `main` once Pages is enabled.

## Safety
This prototype does not connect to exchanges, place orders, or call external AI providers. Never place provider API keys in browser-side files. Real model connections should use a server-side backend with secrets kept server-side. Trading functionality must remain paper/backtest-only unless separately reviewed and deliberately changed.


Deployment trigger: GitHub Pages is configured to publish the `main` branch from the repository root. The static app entry point is `index.html`.
