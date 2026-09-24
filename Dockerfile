# Zweistufig (ARCHITECTURE.md §8): Node baut das Frontend, das Python-Image serviert es.
# Ergebnis ist *ein* Deployable für API und SPA.

FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build


FROM python:3.13-slim AS runtime

# uv statt pip: schnelle, reproduzierbare Installation aus pyproject.toml
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    MEALPLAN_DATA_DIR=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl sqlite3 tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml

COPY backend/src ./src
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
COPY --from=frontend /build/dist ./src/mealplan/static

ENV PYTHONPATH=/app/src

# Auch das Backup-Skript ins Image: die Crontab des Hosts ruft es per
# `docker compose exec` auf (siehe README).
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/backup.sh /app/docker/backup.sh
RUN chmod +x /entrypoint.sh /app/docker/backup.sh && mkdir -p /data

EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
    CMD curl -fsS http://127.0.0.1:8080/api/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
CMD ["uvicorn", "mealplan.main:app", "--host", "0.0.0.0", "--port", "8080"]
