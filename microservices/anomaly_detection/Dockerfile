FROM python:3.10-slim as builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .

RUN pip install --user --no-cache-dir --no-warn-script-location -r requirements.txt

FROM python:3.10-slim

# Метаданные образа
LABEL maintainer="SantiWay ML Team"
LABEL description="Anomaly Detection ML Backend"
LABEL version="1.0.0"

# Создаем non-root пользователя для безопасности
RUN groupadd -r mluser && useradd -r -g mluser mluser

WORKDIR /app

COPY --from=builder /root/.local /home/mluser/.local

COPY --chown=mluser:mluser backend /app/backend
COPY --chown=mluser:mluser models /app/models
COPY --chown=mluser:mluser data /app/data

ENV PATH=/home/mluser/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Переключаемся на non-root пользователя
USER mluser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/anomalies/health', timeout=5)" || exit 1

# Запуск приложения
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
