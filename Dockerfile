FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl netcat-traditional \
  && rm -rf /var/lib/apt/lists/*

# Python зависимости
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Исходники
COPY . /app

# Нерутовый пользователь
RUN useradd -ms /bin/bash app && \
    mkdir -p /static /media && chown -R app:app /static /media

# entrypoint копируем в корень контейнера
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER app

EXPOSE 8000
CMD ["/entrypoint.sh"]
