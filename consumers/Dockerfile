FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Загружаем переменные из окружения (передадим их через docker-compose или docker run)
ENV PYTHONUNBUFFERED=1

CMD ["sh", "-c", "celery -A consumers.celery_app worker -Q $CELERY_QUEUE -n $CELERY_WORKER_NAME@%h -l $CELERY_LOG_LEVEL"]
