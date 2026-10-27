FROM node:22-alpine AS web-build
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data FRONTEND_DIST=/app/frontend/dist
WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir .
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY --from=web-build /build/dist /app/frontend/dist
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin vacabyrock
USER 10001:10001
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=4)" || exit 1
CMD ["sh", "-c", "mkdir -p /data/images /data/audio /data/backups && alembic upgrade head && python -m app.initialize && exec uvicorn app.main:app --host 0.0.0.0 --port 8787"]
