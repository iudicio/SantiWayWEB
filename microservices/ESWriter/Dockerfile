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

# Один-единственный воркер-писатель
# -Q es_writer  — слушаем только очередь писателя
# -c 1          — строго один процесс выполнения
CMD ["celery", "-A", "celery_app.app", "worker", "-Q", "esWriter_queue", "-n", "es-writer", "-c", "1", "--loglevel=INFO"]
