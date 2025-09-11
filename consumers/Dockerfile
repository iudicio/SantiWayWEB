FROM python:3.11-slim-bookworm
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Загружаем переменные из окружения (передадим их через docker-compose или docker run)
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
# Нужно перенести в отдельный .env
ENV CELERY_BROKER_URL=amqp://celery:celerypassword@rabbitmq:5672//
ENV CELERY_WORKER_NAME=worker
ENV CELERY_QUEUE=process_queue
ENV CELERY_LOG_LEVEL=info

RUN mkdir -p /root/.cache && chmod -R 777 /root/.cache
CMD ["sh", "-c", "celery -A celery_app worker -Q $CELERY_QUEUE -n $CELERY_WORKER_NAME@%h -l $CELERY_LOG_LEVEL"]


