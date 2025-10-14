FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY celery_app.py gen_core.py tasks.py ./

CMD ["sh", "-c", "celery -A celery_app worker -Q $CELERY_C_QUEUE_NAME -n $CELERY_CONSUMER_NAME -c 1 -l $CELERY_LOG_LEVEL"]

