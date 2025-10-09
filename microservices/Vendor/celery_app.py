import os

from celery import Celery

broker = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//")

app = Celery("json_processor", broker=broker)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    imports=("tasks",),
    task_acks_late=True,  # ack после успешного выполнения
    worker_prefetch_multiplier=1,
)
