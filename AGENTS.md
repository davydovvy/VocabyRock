# Repository Guidelines

## Project Structure

The FastAPI app, models, migrations, and tests live in `backend/`. The React app and UI tests live in `frontend/`; its browser smoke test is in `frontend/e2e/`. Backup tools live in `scripts/`. Keep contributor documentation in the root or `docs/`.

## Build, Test, and Development

See `README.md` for setup and Synology deployment. Canonical commands: `cd backend && ../.venv/bin/python -m pytest tests -q && ../.venv/bin/ruff check . && ../.venv/bin/ruff format --check .`; `cd frontend && npm run test && npm run lint && npm run format:check && npm run build`; `docker compose up -d --build`. Backend development uses Alembic followed by `python -m app.initialize` before `uvicorn`.

## Coding Style

Follow the conventions of the language and framework selected for each component. Keep formatting consistent within a directory, use descriptive names, and favor small, focused changes. Add the formatter or linter configuration alongside the code it governs, and run it before opening a pull request.

## Testing

Backend tests use pytest; frontend interaction tests use Vitest and Testing Library; `frontend/e2e/smoke.spec.ts` uses Playwright against a running app. Add regression coverage when fixing a defect.

## Commits and Pull Requests

Use concise imperative commit subjects (such as `Add vocabulary import`) and keep unrelated changes in separate commits. Pull requests should explain the change and its motivation, list validation performed, link relevant issues, and include screenshots for user-facing visual changes.

## Configuration and Secrets

Keep credentials and machine-specific settings out of version control. Provide safe example configuration with secrets replaced by placeholders, and document required environment variables when introducing them.
