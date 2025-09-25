import os
from celery import Celery

# Используем вашу конфигурацию RabbitMQ
broker = os.getenv("CELERY_BROKER_URL", "amqp://celery:celerypassword@rabbitmq:5672/")

app = Celery("apkbuild_logger", broker=broker)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    imports=("tasks",),
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        'apkbuild.tasks.log_api_key': {'queue': 'apkbuild'},
        'apkbuild.tasks.log_batch_api_keys': {'queue': 'apkbuild'},
    }
)