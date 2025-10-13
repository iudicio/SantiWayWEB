import os

from celery import Celery

# Используем вашу конфигурацию RabbitMQ
broker = os.getenv("CELERY_BROKER_URL", "amqp://celery:celerypassword@rabbitmq:5672/")

app = Celery("apkbuild", broker=broker)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    imports=("tasks",),
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
