# Anomaly Detection System

Система обнаружения аномалий в активности устройств на основе машинного обучения.

## Возможности

### Детекция аномалий
- **Density Anomalies**: Обнаружение скоплений устройств по регионам
- **Time Anomalies**: Выявление активности в ночное время (0-6 часов)
- **Stationary Anomalies**: Детекция долгого нахождения на одном месте
- **Personal Anomalies**: ML-based детекция через TCN Autoencoder

### Анализ и визуализация
- **SHAP Explainability**: Объяснение почему модель считает точку аномальной
- **Device Comparison**: Сравнение поведения устройств и кластеризация
- **Geo-visualization**: Интерактивная карта аномалий (pydeck)
- **Prometheus Metrics**: Мониторинг производительности системы

### Инфраструктура
- **Real-time Analysis**: FastAPI backend с ClickHouse
- **Interactive Dashboard**: Streamlit frontend с Plotly визуализациями
- **Docker Support**: Полная контейнеризация

## Архитектура

```
Frontend (Streamlit:8501)
         |
Backend (FastAPI:8000)
         |
    ClickHouse:8123
         |
   ML Model (TCN Autoencoder)
```

### Компоненты

- **Backend**: REST API для загрузки данных, анализа и получения результатов
- **Frontend**: Веб-интерфейс с графиками и таблицами
- **ClickHouse**: Колоночная БД с Materialized Views для агрегации
- **ML Model**: TCN Autoencoder для обнаружения аномалий во временных рядах

## Quick Start

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Запуск с Docker Compose

```bash
# Запуск всех сервисов
docker-compose up -d

# Проверка статуса
docker-compose ps
```

### 3. Инициализация базы данных

```bash
python setup_db.py
```

### 4. Загрузка данных в ClickHouse

```bash
curl -X POST "http://localhost:8000/ingest/csv?file_path=data/demo_events.csv"
```

### 5. Обучение модели

**Базовая модель (17 признаков):**
```bash
# Из CSV (локальная разработка)
python ml/train_demo_model.py --source csv

# Из ClickHouse
python ml/train_demo_model.py --source clickhouse
```

**Продвинутая модель (67 признаков + Attention):**
```bash
# Полное обучение с расширенными признаками
python ml/train_advanced_model.py --days 3 --epochs 50 --use-extended --use-attention

# Параметры:
# --days N          Количество дней данных для обучения
# --epochs N        Количество эпох (default: 50)
# --lr 0.001        Learning rate (default: 0.001)
# --use-extended    Использовать 67 признаков (default: True)
# --use-attention   Использовать Multi-Head Attention (default: True)
# --device cpu|cuda Устройство для обучения
```

### 6. Тестирование модели

**Базовая модель:**
```bash
python ml/test_demo_model.py
```

**Продвинутая модель:**
```bash
python ml/test_advanced_model.py
```

### 7. Открытие dashboard

```
http://localhost:8501
```

## API Endpoints

### Ingest (загрузка данных)
- `POST /ingest/events` - Загрузка событий в JSON формате
- `POST /ingest/csv` - Загрузка из CSV файла

### Analysis (анализ)
- `POST /analyze/global` - Глобальный анализ всех устройств
- `POST /analyze/device/{device_id}` - Анализ конкретного устройства

### Anomalies (результаты)
- `GET /anomalies` - Получение списка аномалий с фильтрацией
- `GET /anomalies/stats` - Статистика за 24 часа

### Comparison (сравнение устройств)
- `POST /comparison/similar` - Поиск похожих устройств
- `POST /comparison/clusters` - Детекция кластеров поведения
- `POST /comparison/compare` - Сравнение двух устройств
- `POST /comparison/coordinated` - Поиск координированных устройств
- `GET /comparison/profiles` - Профили всех устройств

### Explain (объяснение аномалий)
- `POST /explain/device` - SHAP-объяснение аномалий устройства
- `GET /explain/features` - Описания всех признаков
- `POST /explain/compare-explanations` - Сравнение объяснений

### Monitoring
- `GET /metrics` - Prometheus метрики
- `GET /health` - Health check

### Примеры запросов

```bash
# Глобальный анализ
curl -X POST "http://localhost:8000/analyze/global" \
  -H "Content-Type: application/json" \
  -d '{"period": "24h", "detection_types": ["density", "time", "personal"]}'

# Анализ устройства
curl -X POST "http://localhost:8000/analyze/device/device_0050" \
  -H "Content-Type: application/json" \
  -d '{"period": "24h"}'

# Получение аномалий
curl "http://localhost:8000/anomalies?limit=100&min_score=0.5"

# Поиск похожих устройств
curl -X POST "http://localhost:8000/comparison/similar" \
  -H "Content-Type: application/json" \
  -d '{"device_id": "device_0050", "top_k": 10, "min_similarity": 0.8}'

# SHAP-объяснение аномалий
curl -X POST "http://localhost:8000/explain/device" \
  -H "Content-Type: application/json" \
  -d '{"device_id": "device_0050", "hours": 168, "top_k": 5}'

# Prometheus метрики
curl http://localhost:8000/metrics
```

## ML Models

Система поддерживает две модели с разным уровнем сложности:

### 1. Базовая модель (TCN Autoencoder)

**Архитектура:**
- Encoder: 3 TemporalBlock с dilated causal convolution (dilation: 1, 2, 4)
- Bottleneck: Linear layer (256 -> 64)
- Decoder: 3 ConvTranspose1d слоя

**Параметры:**
- Input channels: 17
- Hidden channels: [64, 128, 256]
- Kernel size: 3
- Window size: 24 часа
- Размер модели: ~7 MB

**Признаки (17 базовых):**
- event_count, avg_activity, std_activity
- avg_lat, avg_lon, hour
- velocity, acceleration, bearing_change
- location_entropy, stationarity_score
- hour_sin, hour_cos, is_night
- min_activity, max_activity, activity_range, p95_activity

### 2. Продвинутая модель (TCN Autoencoder Advanced)

**Архитектура:**
- Encoder: 3 TemporalBlock с dilated causal convolution
- **Multi-Head Attention** (8 heads) для temporal dependencies
- Bottleneck: Linear layer (256 -> 128)
- Decoder: 3 ConvTranspose1d слоя с skip connections

**Параметры:**
- Input channels: 67 (расширенные признаки)
- Hidden channels: [64, 128, 256]
- Attention heads: 8
- Kernel size: 3
- Window size: 24 часа
- Размер модели: ~233 MB

**Расширенные признаки (67 total):**

*Базовые (17):*
- event_count, avg_activity, std_activity
- avg_lat, avg_lon, hour
- velocity, acceleration, bearing_change
- location_entropy, stationarity_score
- hour_sin, hour_cos, is_night
- min_activity, max_activity, activity_range, p95_activity

*Статистические (7):*
- skewness, kurtosis (асимметрия и эксцесс)
- quantile_25, quantile_50, quantile_75
- coefficient_of_variation, interquartile_range

*Rolling features (12):*
- rolling_mean, rolling_std, rolling_min, rolling_max (окно 3ч и 6ч)

*Autocorrelation (6):*
- lag_1, lag_3, lag_6, lag_12, lag_24

*Spatial advanced (15):*
- spatial_dispersion, convex_hull_area, radius_of_gyration
- trajectory_entropy, movement_efficiency
- direction_consistency, spatial_autocorrelation

*Behavioral patterns (10):*
- peak_hour, peak_activity_ratio
- day_night_ratio, work_hours_ratio
- weekend_ratio, routine_score

### Сравнение моделей

| Характеристика | Базовая | Продвинутая |
|----------------|---------|-------------|
| Признаки | 17 | 67 |
| Multi-Head Attention | ❌ | ✅ (8 heads) |
| Размер модели | ~7 MB | ~233 MB |
| Время инференса | ~10ms | ~50ms |
| Точность | Хорошая | Отличная |
| Требования к памяти | Низкие | Высокие |
| Использование | Прототипирование, production с ограничениями | Production, максимальная точность |

### Выбор модели

**Базовая модель (tcn_model.pt)** - рекомендуется для:
- Быстрого прототипирования
- Систем с ограниченными ресурсами
- Real-time обработки с низкой latency
- Простых паттернов аномалий

**Продвинутая модель (tcn_advanced_model.pt)** - рекомендуется для:
- Максимальной точности детекции
- Сложных временных зависимостей
- Детального анализа поведения
- Production систем с достаточными ресурсами

### Пороги аномалий
- 95 percentile: используется для детекции
- 99 percentile: для критических аномалий

## База данных

### Таблицы

**events** - сырые события устройств
- timestamp, device_id, lat, lon, activity_level, region
- TTL: 90 дней
- Партицирование по месяцам

**anomalies** - результаты детекции
- detected_at, timestamp, device_id, anomaly_type, anomaly_score, region, details
- TTL: 180 дней
- Типы: density_spike, time_anomaly, personal_deviation, spatial_outlier

### Materialized Views

- **hourly_features** - агрегация по часам (event_count, avg/std activity, координаты)
- **regional_density** - плотность по регионам
- **daily_features** - дневная статистика

## Структура проекта

```
test_nn/
├── backend/
│   ├── main.py                      # FastAPI приложение
│   ├── routes/
│   │   ├── ingest.py                # Загрузка данных
│   │   ├── analyze.py               # Анализ устройств
│   │   ├── anomalies.py             # Получение результатов
│   │   ├── comparison.py            # Сравнение устройств
│   │   └── explain.py               # SHAP объяснения
│   ├── services/
│   │   ├── clickhouse_client.py     # Клиент БД
│   │   ├── anomaly_detector.py      # Детектор аномалий
│   │   ├── feature_engineer.py      # Инженерия признаков
│   │   ├── model_tcn.py             # TCN Autoencoder (базовая)
│   │   ├── model_tcn_advanced.py    # TCN Advanced + Attention
│   │   ├── model_manager.py         # Управление моделями
│   │   ├── device_comparison.py     # Сравнение и кластеризация
│   │   ├── explainer.py             # SHAP explainability
│   │   └── metrics.py               # Prometheus метрики
│   └── utils/
│       └── config.py                # Конфигурация
├── frontend/
│   ├── app.py                       # Streamlit dashboard
│   └── components/
│       └── map_view.py              # Geo-visualization (pydeck)
├── ml/
│   ├── train_demo_model.py          # Обучение базовой модели
│   ├── test_demo_model.py           # Тестирование базовой модели
│   ├── train_advanced_model.py      # Обучение продвинутой модели
│   ├── test_advanced_model.py       # Тестирование продвинутой модели
│   └── utils/
│       └── dataset_builder.py       # Построение датасетов
├── tests/
│   ├── test_api.py                  # Тесты API endpoints
│   ├── test_feature_engineer.py     # Тесты признаков
│   └── test_models.py               # Тесты моделей
├── clickhouse/
│   ├── schema.sql                   # Схема таблиц
│   └── views.sql                    # Materialized Views
├── models/
│   ├── tcn_model.pt                 # Базовая модель (~7 MB)
│   ├── model_metadata.json          # Метаданные базовой модели
│   ├── tcn_advanced_model.pt        # Продвинутая модель (~233 MB)
│   ├── model_metadata_advanced.json # Метаданные продвинутой модели
│   ├── test_results.png             # Результаты тестов базовой
│   └── test_advanced_results.png    # Результаты тестов продвинутой
├── data/
│   ├── demo_events.csv              # Демо-данные
│   └── gen_data.py                  # Генератор синтетических данных
├── docker-compose.yml               # Docker конфигурация
├── Dockerfile                       # Backend образ
├── requirements.txt                 # Python зависимости
├── setup_db.py                      # Инициализация БД
├── pytest.ini                       # Конфигурация pytest
└── README.md
```

## Development

### Локальная разработка без Docker

```bash
# Terminal 1: ClickHouse
docker run -d -p 8123:8123 -p 9000:9000 clickhouse/clickhouse-server

# Инициализация БД
python setup_db.py

# Terminal 2: Backend
export PYTHONPATH=$PWD
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3: Frontend
streamlit run frontend/app.py --server.port 8501
```

### Конфигурация

Переменные окружения (или .env файл):

```bash
# ClickHouse
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=
CLICKHOUSE_DATABASE=anomaly_demo

# API
API_HOST=0.0.0.0
API_PORT=8000

# ML
MODEL_PATH=models/tcn_model.pt
DEVICE=cpu
BATCH_SIZE=64
WINDOW_SIZE=24
ANOMALY_THRESHOLD_95=0.089
ANOMALY_THRESHOLD_99=0.145
```

### Тестирование

```bash
# Health check
curl http://localhost:8000/health

# Unit tests (pytest)
pytest tests/ -v

# Тест конкретного модуля
pytest tests/test_feature_engineer.py -v
pytest tests/test_models.py -v
pytest tests/test_api.py -v

# Тест базовой модели
python ml/test_demo_model.py

# Тест продвинутой модели
python ml/test_advanced_model.py
```

## Типы аномалий

| Тип | Описание | Метод детекции |
|-----|----------|----------------|
| density_spike | Скопление устройств в регионе | Z-score > 2 от среднего |
| time_anomaly | Активность в ночное время | Час 0-6, Z-score > 3 |
| night_activity | Ночная активность | Классификация time_anomaly |
| stationary_surveillance | Долгое наблюдение | Низкая мобильность + высокая активность |
| personal_deviation | Индивидуальное отклонение | TCN Autoencoder reconstruction error |
| following | Преследование | Классификация personal_deviation |

## SHAP Explainability

Система объясняет почему модель считает точку аномальной с помощью SHAP (SHapley Additive exPlanations).

### Возможности
- Вычисление вклада каждого признака в anomaly score
- Gradient-based fallback при ошибках SHAP
- Агрегация по временным шагам
- Человекочитаемые описания

### Пример ответа
```json
{
  "top_features": [
    {
      "feature": "avg_activity",
      "importance": 0.45,
      "direction": "increases",
      "description": "Average activity level - unusually high value contributes to anomaly"
    }
  ],
  "method": "shap"
}
```

## Device Comparison

Сравнение поведенческих паттернов устройств для выявления похожего поведения.

### Методы
- **Cosine Similarity** - поиск похожих устройств по профилю
- **DBSCAN Clustering** - автоматическая группировка по поведению
- **Coordinated Detection** - поиск устройств в одном месте в одно время

### Профиль устройства
10 признаков для сравнения:
- avg_activity, std_activity, min_activity, max_activity
- std_lat, std_lon (mobility)
- unique_regions
- avg_hour, night_ratio, work_ratio

## Prometheus Metrics

Мониторинг производительности через Prometheus.

### Доступные метрики

**API метрики:**
- `anomaly_api_requests_total` - счётчик запросов
- `anomaly_api_request_latency_seconds` - latency histogram

**Модель:**
- `model_inference_total` - количество инференсов
- `model_inference_latency_seconds` - время инференса
- `model_anomaly_scores` - распределение scores

**База данных:**
- `clickhouse_queries_total` - количество запросов
- `clickhouse_query_latency_seconds` - latency запросов

**Система:**
- `active_devices_count` - активные устройства
- `total_events_count` - всего событий
- `pending_anomalies_count` - необработанные аномалии

### Интеграция с Grafana
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'anomaly-detection'
    static_configs:
      - targets: ['localhost:8000']
```

## Geo-visualization

Интерактивная карта аномалий на основе pydeck.

### Возможности
- ScatterplotLayer с цветовым кодированием по типу
- Размер точки пропорционален anomaly_score
- Tooltip с информацией об аномалии
- Легенда типов аномалий

### Цветовая схема
- Красный: density_cluster
- Синий: night_activity
- Оранжевый: stationary_surveillance
- Фиолетовый: personal_deviation
- Жёлтый: following

## Зависимости

- Python >= 3.10
- PyTorch >= 2.6.0
- FastAPI >= 0.104.1
- ClickHouse Connect >= 0.6.23
- Streamlit >= 1.28.0
- Pandas >= 2.1.0
- NumPy >= 1.26.0
- Plotly >= 5.18.0
- scikit-learn >= 1.4.0
- SHAP >= 0.44.0
- prometheus-client >= 0.19.0
- pydeck >= 0.8.1

