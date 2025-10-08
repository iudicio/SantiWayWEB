FROM python:3.11-slim-bookworm
WORKDIR /app

# Системные зависимости (curl для загрузки OUI, если нужно)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl build-essential && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY celery_app.py tasks.py tests.py vendorsFunc.py mac-vendors.json ./

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN mkdir -p /app/cache

RUN addgroup --system celery && adduser --system --ingroup celery celery \
    && mkdir -p /app/cache && chown -R celery:celery /app
USER celery

CMD ["sh", "-c", "celery -A celery_app worker -Q $CELERY_C_QUEUE_NAME -n $CELERY_CONSUMER_NAME -l $CELERY_LOG_LEVEL"]
