# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# --- Local development: adds test tooling; source is bind-mounted by compose.
FROM base AS dev
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY . .
EXPOSE 8000

# --- Production image (default target, used by CI and Cloud Run).
FROM base AS prod
RUN useradd --create-home --uid 1000 app
COPY . .
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && chown -R app:app /app
USER app
# Cloud Run injects PORT (8080 by default).
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 60"]
