# Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Ставим зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Кладём исходники
COPY celery_app.py es_writer.py tasks.py ./

# -c 1 — строго один процесс выполнения
CMD ["sh", "-c", "celery -A celery_app worker -Q $CELERY_C_QUEUE_NAME -n $CELERY_CONSUMER_NAME -c 1 -l $CELERY_LOG_LEVEL"]
