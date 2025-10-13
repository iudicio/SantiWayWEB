# celery_app.py
import os

from celery import Celery

broker = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//")

app = Celery("esWriter", broker=broker)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    imports=("tasks",),  # импортируем файл с тасками
    task_acks_late=True,  # ack только после успешного выполнения
    worker_prefetch_multiplier=1,  # воркер берёт по одной задаче
)
