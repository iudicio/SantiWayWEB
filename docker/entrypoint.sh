#!/usr/bin/env bash
set -e

# Ждём Postgres
: "${POSTGRES_HOST:=postgres}"
: "${POSTGRES_PORT:=5432}"

echo "Waiting for Postgres at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
until nc -z "${POSTGRES_HOST}" "${POSTGRES_PORT}"; do
  sleep 1
done

# Ждём Elasticsearch, если указан
if [ -n "${ES_URL}" ]; then
  echo "Waiting for Elasticsearch at ${ES_URL}..."
  until curl -sf "${ES_URL}" >/dev/null; do
    sleep 2
  done
fi

# Миграции и суперпользователь
python manage.py migrate --noinput

# Статика
python manage.py collectstatic --noinput

if [ -n "${DJANGO_SUPERUSER_EMAIL}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD}" ]; then
python - <<'PY'
import os, django
django.setup()
from django.contrib.auth import get_user_model
try:
    User = get_user_model()
    email=os.environ["DJANGO_SUPERUSER_EMAIL"]
    password=os.environ["DJANGO_SUPERUSER_PASSWORD"]
    if not User.objects.filter(email=email).exists():
        # username=email — если используется кастомная модель с email, подправьте при необходимости
        User.objects.create_superuser(username=email, email=email, password=password)
    print("Superuser ensured")
except Exception as e:
    print(f"Superuser creation skipped: {e}")
PY
fi

mkdir -p /app/staticfiles /app/media

# Запуск Gunicorn
exec gunicorn SantiWayWEB.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --threads "${GUNICORN_THREADS:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-60}"
