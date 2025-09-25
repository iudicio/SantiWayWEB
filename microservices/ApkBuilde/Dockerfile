FROM python:3.11-slim-bookworm
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl build-essential && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY celery_app.py build_apk.py tasks.py ./

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN addgroup --system celery && adduser --system --ingroup celery celery \
    && mkdir -p /app/logs && chown -R celery:celery /app
USER celery

CMD ["sh", "-c", "celery -A celery_app worker -Q apkbuild -n apkbuild@%h -l info"]