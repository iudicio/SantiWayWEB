# celery_app.py
from os import getenv

from celery import Celery

broker = getenv("CELERY_BROKER_URL", "amqp://celery:celerypassword@rabbitmq:5672//")
backend = getenv("BACKEND_URL", "redis://:strongpassword@redis:6379/0")

app = Celery("userInfo", broker=broker, backend=backend)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    imports=("tasks",),  # импортируем файл с тасками
    task_acks_late=True,  # ack только после успешного выполнения
    worker_prefetch_multiplier=1,  # воркер берёт по одной задаче
)
