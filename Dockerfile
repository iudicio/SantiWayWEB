FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl netcat-traditional libpq5 dos2unix \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

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
RUN dos2unix /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8000
CMD ["/entrypoint.sh"]
