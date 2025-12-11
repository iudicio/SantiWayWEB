# Anomaly Detection System

ML-система обнаружения аномалий в активности устройств. Работает на production данных из ClickHouse, отправляет уведомления через WebSocket.

**Production-Ready:** SQL Injection защита, Rate Limiting, API Key Auth, Connection Pooling, Retry Logic

---

### 1. Запуск через Docker

```bash
# Из корня проекта SantiWay
docker-compose up ml_backend ml_frontend -d

# Проверка
curl http://localhost/ml/health
# Frontend: http://localhost:8501
```

### 2. Создать ClickHouse views (ПЕРВЫЙ ЗАПУСК)

```bash
docker exec -it santi_clickhouse clickhouse-client

# Выполнить:
CREATE DATABASE IF NOT EXISTS anomaly_ml;
```

Затем выполнить SQL из файлов:
- `clickhouse/schema.sql` - создание таблиц
- `clickhouse/views.sql` - materialized views

```bash
docker exec -i santi_clickhouse clickhouse-client --multiquery < anomaly_detection/clickhouse/schema.sql
docker exec -i santi_clickhouse clickhouse-client --multiquery < anomaly_detection/clickhouse/views.sql
```

### 3. Обучить модель

```bash
cd anomaly_detection
pip install -r requirements.txt
python ml/train_model.py
```

Обучается на **30 днях production данных** из `santi.way_data`.
Результат: `models/tcn_model.pt` + метаданные (98 features).

### 4. Проверить работу

```bash
# API endpoints (через nginx)
curl http://localhost/ml/anomalies/stats

# WebSocket notifications (API key через HTTP Header)
curl -X POST "http://localhost/ml/anomalies/detect-and-notify?hours=24" \
  -H "X-API-Key: YOUR_API_KEY"
```

---

## Архитектура

### Поток данных

```
Вендор устройств
    ↓
ClickHouse (santi.way_data) ← Production данные
    ↓
Materialized Views (anomaly_ml.hourly_features)
    ↓
ML Backend (FastAPI) - Async Pool + Retry Logic
    ├─→ Детекция аномалий (Rate Limited)
    ├─→ Сохранение в anomaly_ml.anomalies
    └─→ WebSocket уведомления (через Django с Retry)
```

### Технологии

- **Backend**: FastAPI + PyTorch (TCN Autoencoder)
- **Database**: ClickHouse с async pool (`asynch` library)
- **Features**: 98 признаков (signal, spatial, temporal, network, vendor)
- **Security**: SQL Injection protection, Rate Limiting, API Key validation
- **Reliability**: Retry logic (tenacity), Connection pooling
- **Notifications**: WebSocket через Django Channels
- **Frontend**: Streamlit dashboard

### Детекторы аномалий

1. **Density Anomalies** - скопления устройств в папках
2. **Time Anomalies** - активность ночью (0-6 часов)
3. **Stationary Surveillance** - стационарное наблюдение
4. **Personal ML Detector** - TCN Autoencoder на 98 фичах

---

## Security Features

### SQL Injection Protection

Все запросы используют **parameterized queries**:

```python
# Защищено от SQL injection
query = "SELECT * FROM anomalies WHERE device_id = %s"
result = await ch_client.query(query, [device_id])
```

- Валидация table/column names через regex
- Безопасная передача параметров
- Логирование всех запросов

### API Key Authentication

**Безопасность:** API ключ передается через HTTP Header `X-API-Key` (не в URL!)

```bash
# .env
VALID_API_KEYS=key1,key2,key3

# Или оставить пустым для dev mode (без проверки)
VALID_API_KEYS=
```

**Генерация безопасного ключа:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Правильное использование (Header-based):**
```bash
curl -X POST "http://localhost/ml/anomalies/detect-and-notify?hours=24" \
  -H "X-API-Key: YOUR_SECRET_KEY"
```

**Старый способ (небезопасный, не работает):**
```bash
# Не используйте - ключ попадает в логи/URL!
curl -X POST "http://localhost/ml/anomalies/detect-and-notify?api_key=YOUR_KEY&hours=24"
```

### Rate Limiting

Защита от DDoS и abuse:

| Endpoint | Limit | Описание |
|----------|-------|----------|
| `GET /anomalies` | 100/min | Список аномалий |
| `POST /detect-and-notify` | 10/min | Детекция (resource-intensive) |

При превышении лимита: **HTTP 429 Too Many Requests**

### CORS Security

```bash
# .env
ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com

# Dev mode
ALLOWED_ORIGINS=http://localhost,http://localhost:3000
```

### Retry Logic

Автоматический retry при сбоях:

| Операция | Попытки | Backoff | Retry на |
|----------|---------|---------|----------|
| ClickHouse Connect | 5 | 2s → 30s | Connection/Timeout/OSError |
| ClickHouse Query | 3 | 1s → 10s | Connection/Timeout/OSError |
| HTTP to Django | 3 | 1s → 10s | HTTPError/Timeout |

---

## API Endpoints

**Base URL**: `http://localhost/ml/` (через nginx)

### Health & Monitoring

- `GET /health` - health check с диагностикой
- `GET /metrics` - Prometheus metrics

### Аномалии

- `GET /anomalies?limit=100&device_id=XXX` - список аномалий
  - **Rate Limit:** 100/minute
  - **Params:** limit, anomaly_type, min_score, device_id

- `GET /anomalies/stats` - статистика за 24h

- `POST /anomalies/detect-and-notify?hours=24`
  - **Rate Limit:** 10/minute
  - **Auth:** API Key required (HTTP Header: `X-API-Key`)
  - Запускает детекцию + отправку через WebSocket
  - **Пример:**
    ```bash
    curl -X POST "http://localhost/ml/anomalies/detect-and-notify?hours=24" \
      -H "X-API-Key: YOUR_SECRET_KEY"
    ```

### Анализ

- `POST /analyze/device/{device_id}?hours=24` - анализ устройства
- `POST /comparison/compare` - сравнение устройств

### SHAP Explainability

- `POST /explain/device` - объяснение аномалий (SHAP values)

---

## WebSocket Notifications

### Архитектура

```
ML Backend (FastAPI)
    ↓ HTTP POST with Retry Logic
Django /notifications/api/send/
    ↓ Channels
WebSocket Clients (ws://host/ws/notifications/?api_key=KEY)
```

### Подключение (JavaScript)

```javascript
const ws = new WebSocket('ws://YOUR_HOST/ws/notifications/?api_key=YOUR_API_KEY');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'anomaly.detected') {
    console.log('Аномалия:', data.anomaly);
    // severity: 'critical' | 'warning' | 'info'
    // anomaly: {device_id, type, score, folder, vendor, ...}
  }
};

ws.onerror = (error) => console.error('WebSocket error:', error);
ws.onclose = () => console.log('Disconnected');
```

### Формат уведомления

```json
{
  "type": "anomaly.detected",
  "severity": "critical",
  "title": "КРИТИЧНО: Скопление устройств",
  "text": "Устройство: AA:BB:CC... | Папка: office | Оценка: 85.3%",
  "anomaly": {
    "device_id": "AA:BB:CC:DD:EE:FF",
    "type": "density_spike",
    "score": 0.853,
    "folder": "office",
    "vendor": "Apple Inc.",
    "network_type": "wifi",
    "details": {
      "unique_devices": 150,
      "p95_baseline": 80
    }
  },
  "coords": {
    "lat": 55.7558,
    "lon": 37.6173
  }
}
```

---

## ML Model (TCN Autoencoder)

### Признаки (98 total)

**Базовые (20)**: event_count, signal_strength, spatial, velocity, temporal, network_type

**Расширенные (+50)**: статистика, rolling windows, autocorrelation, behavioral patterns

**Advanced (+28)**: signal dynamics, network patterns, vendor behavior, cross-interactions

### Обучение

```bash
python ml/train_model.py
```

**Что происходит:**
1. Загрузка 30 дней данных из `anomaly_ml.hourly_features`
2. Глобальная нормализация статистик (mean/std для 98 features)
3. Генерация 98 признаков для каждого устройства
4. Обучение TCN Autoencoder (reconstruction error → anomaly score)
5. Early stopping + best model сохранение
6. Расчет thresholds (95th, 99th percentile)

**Результат:**
- `models/tcn_model.pt` (~200MB)
- `models/model_metadata.json` (thresholds, normalization, 98 features)

### Advanced модель

```bash
python ml/train_advanced_model.py --days 30 --epochs 50 --use-attention
```

TCN + Multi-Head Attention + больше hidden channels для лучшей точности.

---

## Конфигурация

### Environment Variables (.env)

```bash
# ClickHouse (Async Pool)
CLICKHOUSE_HOST=clickhouse
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=anomaly_ml
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=

# Security
ALLOWED_ORIGINS=http://localhost,http://localhost:8000,http://localhost:3000
VALID_API_KEYS=  # Empty = dev mode (no validation)

# Model
MODEL_PATH=models/tcn_model.pt
INPUT_CHANNELS=98
DEVICE=auto  # auto | cuda | mps | cpu
WINDOW_SIZE=24
BATCH_SIZE=32

# Thresholds (overridden by model_metadata.json)
ANOMALY_THRESHOLD_95=0.87
ANOMALY_THRESHOLD_99=0.92

# API
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=True

# Django (для WebSocket notifications)
DJANGO_URL=http://web:8000
```

### Docker Compose

Сервисы в главном `docker-compose.yml`:
- `ml_backend` (port 8001, exposed через nginx /ml/)
- `ml_frontend` (port 8501, Streamlit dashboard)

---

## Структура проекта

```
anomaly_detection/
├── backend/
│   ├── main.py                      # FastAPI app + Rate Limiting
│   ├── routes/                      # API endpoints
│   │   ├── anomalies.py            # Детекторы + API Key validation
│   │   ├── analyze.py              # Анализ устройств
│   │   ├── explain.py              # SHAP explainability
│   │   └── comparison.py           # Сравнение устройств
│   ├── services/
│   │   ├── anomaly_detector.py     # 4 типа детекторов
│   │   ├── feature_engineer.py     # 98 признаков
│   │   ├── model_tcn.py            # TCN Autoencoder
│   │   ├── clickhouse_client.py    # Async Pool + Retry + SQL Injection Protection
│   │   ├── notification_service.py # WebSocket + Retry Logic
│   │   └── data_validator.py       # Data quality validation
│   └── utils/
│       └── config.py               # Settings (CORS, API Keys, etc.)
├── ml/
│   ├── train_model.py              # Обучение модели
│   ├── test_model.py               # Тестирование
│   └── train_advanced_model.py     # Advanced TCN + Attention
├── clickhouse/
│   ├── schema.sql                  # Таблицы с индексами
│   └── views.sql                   # Materialized views
├── models/
│   ├── tcn_model.pt                # Обученная модель
│   └── model_metadata.json         # Метаданные + normalization
├── frontend/
│   └── app.py                      # Streamlit dashboard
└── requirements.txt                # Dependencies (asynch, tenacity, slowapi)
```

---

## Troubleshooting

### Модель не загружается

```
Error: Model file not found
```

**Решение:** Обучить модель
```bash
cd anomaly_detection
python ml/train_model.py
```

### Нет данных для обучения

```
No data found. Make sure materialized views are populated.
```

**Решение:** Проверить ClickHouse
```sql
-- Должны вернуть данные
SELECT count() FROM santi.way_data;
SELECT count() FROM anomaly_ml.hourly_features;

-- Если hourly_features пустой, materialized view не заполнилась
-- Проверить что данные в way_data появились ПОСЛЕ создания view
```

### Size mismatch error

```
RuntimeError: size mismatch (expected 98, got XX)
```

**Решение:** Переобучить модель на 98 фичах
```bash
python ml/train_model.py
```

Проверить конфиг:
```bash
grep INPUT_CHANNELS .env
# Должно быть: INPUT_CHANNELS=98
```

### Rate Limit Error (429)

```
HTTP 429 Too Many Requests
```

**Причина:** Превышен лимит запросов

**Решение:**
- Подождать 1 минуту
- Уменьшить частоту запросов
- Для production: настроить индивидуальные лимиты

### API Key Invalid (401)

```
HTTP 401 Unauthorized: Invalid API key
```

**Решение:**
```bash
# Проверить .env
grep VALID_API_KEYS .env

# Должно содержать ваш ключ, или быть пустым для dev mode
VALID_API_KEYS=your-key-here
```

### WebSocket не получает уведомления

**Проверить:**
1. Django Channels работает: `docker logs santi_web | grep channels`
2. API key правильный
3. URL правильный: `ws://host/ws/notifications/?api_key=KEY`
4. Backend может достучаться до Django (`DJANGO_URL` в .env)

**Тест:**
```bash
# Запустить детекцию (API key через Header)
curl -X POST "http://localhost/ml/anomalies/detect-and-notify?hours=24" \
  -H "X-API-Key: YOUR_SECRET_KEY"

# Проверить логи ML backend
docker logs anomaly_ml_backend | grep "notification"

# Должны увидеть:
# "Anomaly notification sent via Django API"
```

### ClickHouse Connection Failed

```
ClickHouse connection pool failed: Connection refused
```

**Решение:**
```bash
# Проверить что ClickHouse запущен
docker ps | grep clickhouse

# Проверить network
docker network inspect app-network | grep ml_backend

# Перезапустить
docker-compose restart clickhouse ml_backend
```

### High False Positive Rate

**Решения:**
1. Увеличить threshold в `model_metadata.json` или `.env`
2. Переобучить на большем объеме данных (60-90 дней)
3. Откалибровать на реальной статистике вашего deployment

---


### Production .env Example

```bash
# ClickHouse (internal network only)
CLICKHOUSE_HOST=clickhouse
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=anomaly_ml

# Security
ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com
VALID_API_KEYS=<STRONG_RANDOM_KEY_1>,<STRONG_RANDOM_KEY_2>

# Model
MODEL_PATH=models/tcn_model.pt
INPUT_CHANNELS=98
DEVICE=cpu

# Django
DJANGO_URL=http://web:8000
```

### Monitoring & Alerting

**Prometheus Metrics:**
```bash
curl http://localhost/ml/metrics
```

**Health Check:**
```bash
curl http://localhost/ml/health
```

Мониторить:
- `anomaly_detection_requests_total` - количество запросов
- `anomaly_detection_request_duration_seconds` - latency
- HTTP 429 responses - возможная DDoS атака
- HTTP 401 responses - brute force попытки
- ClickHouse connection retries - проблемы с БД

**Logs:**
```bash
# ML Backend
docker logs anomaly_ml_backend -f --tail 100

# ClickHouse
docker logs santi_clickhouse -f --tail 100

# Django (WebSocket)
docker logs santi_web -f | grep notification
```

### Переобучение модели

Рекомендуется **раз в месяц** или при изменении паттернов:

```bash
# 1. Обучить новую модель
python ml/train_model.py

# 2. Проверить метаданные
cat models/model_metadata.json
# Должно быть: "input_channels": 98, "data_source": "production_way_data"

# 3. Restart backend для загрузки новой модели
docker-compose restart ml_backend

# 4. Проверить health
curl http://localhost/ml/health
# Должно быть: "model_loaded": true
```

### Backup & Recovery

**Модель:**
```bash
# Backup
cp models/tcn_model.pt models/tcn_model_backup_$(date +%Y%m%d).pt
cp models/model_metadata.json models/model_metadata_backup_$(date +%Y%m%d).json

# Recovery
cp models/tcn_model_backup_YYYYMMDD.pt models/tcn_model.pt
docker-compose restart ml_backend
```

---

## Development

### Local Setup

```bash
# 1. Install dependencies
cd anomaly_detection
pip install -r requirements.txt

# 2. Configure .env
cp .env.example .env
nano .env

# 3. Run locally (без Docker)
python -m uvicorn backend.main:app --reload --port 8001

# 4. Test
curl http://localhost:8001/health
```

### Testing

```bash
# API tests
curl http://localhost/ml/health
curl http://localhost/ml/anomalies/stats

# Rate limiting test (должен вернуть 429 после 100)
for i in {1..105}; do curl http://localhost/ml/anomalies; done

# SQL injection test (должен быть защищен)
curl "http://localhost/ml/anomalies?device_id=test'; DROP TABLE anomalies;--"

# API key validation test (Header-based)
curl -X POST "http://localhost/ml/anomalies/detect-and-notify?hours=24" \
  -H "X-API-Key: invalid_key"
# Expected: HTTP 401 Unauthorized

# Missing API key test
curl -X POST "http://localhost/ml/anomalies/detect-and-notify?hours=24"
# Expected: HTTP 401 "Missing API key. Provide X-API-Key header."
```

---

## Dependencies

```txt
# Core
fastapi>=0.104.1
uvicorn[standard]>=0.24.0
pydantic>=2.10.0

# Database (Async Pool)
asynch>=0.2.3

# ML
torch>=2.6.0
numpy>=1.26.0
pandas>=2.1.0

# Security & Reliability
tenacity>=8.2.3       # Retry logic
slowapi>=0.1.9        # Rate limiting

# Monitoring
prometheus-client>=0.19.0
loguru>=0.7.2
```

---

## Documentation Links

- **Integration Guide**: [INTEGRATION_GUIDE.md](../INTEGRATION_GUIDE.md)
- **Security Audit**: See commit history for security improvements
- **API Docs**: `http://localhost:8001/docs` (Swagger UI)

---

## Tips & Best Practices

1. **Never commit** `.env` file - содержит секреты
2. **Rotate API keys** регулярно (каждые 90 дней)
3. **Monitor 429 responses** - индикатор DDoS или misconfiguration
4. **Monitor retry rate** - индикатор проблем с инфраструктурой
5. **Retrain model monthly** на свежих данных
6. **Backup model** перед переобучением
7. **Use strong API keys** - минимум 32 символа random
8. **Enable HTTPS** в production для защиты credentials
9. **Restrict ClickHouse** доступ только к internal network
10. **Monitor data quality** через `/health` endpoint

---

## Support

**Проблемы с:**
- ClickHouse → `docker logs santi_clickhouse`
- ML Backend → `docker logs anomaly_ml_backend`
- WebSocket → `docker logs santi_web | grep channels`
- Nginx → `docker logs santi_nginx`

**Debug mode:**
```bash
# В .env
LOG_LEVEL=DEBUG
API_RELOAD=True
```

**Common Commands:**
```bash
# Запуск
docker-compose up ml_backend ml_frontend -d

# Обучение
python ml/train_model.py

# Детекция + уведомления (Header-based Auth)
curl -X POST "http://localhost/ml/anomalies/detect-and-notify?hours=24" \
  -H "X-API-Key: YOUR_SECRET_KEY"

# Health check
curl http://localhost/ml/health

# Metrics
curl http://localhost/ml/metrics

# Logs
docker logs anomaly_ml_backend -f
```

---

