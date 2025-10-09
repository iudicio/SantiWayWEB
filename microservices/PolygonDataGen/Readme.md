# Микросервис PolygonDataGen

Потребитель Celery, который генерирует синтетические записи устройств и ПУБЛИКУЕТ их в микросервис ESWriter для индексации в Elasticsearch; примерно ~20% точек находятся внутри заданного полигона. Разработан для последующего использования в признаках на основе полигона и детектировании аномалий.

## Переменные окружения
- `CELERY_BROKER_URL` (AMQP URL)
- `CELERY_C_TASK_NAME` (по умолчанию: `polygons.generate_data`)
- `CELERY_C_QUEUE_NAME` (по умолчанию: `polygon_gen`)
- `CELERY_CONSUMER_NAME` (например, `polygon-data-gen@%h`)
- `CELERY_LOG_LEVEL` (например, `info`)
- Маршрутизация в ESWriter:
  - `ESWRITER_TASK_NAME` (по умолчанию: `esWriter`)
  - `ESWRITER_QUEUE_NAME` (по умолчанию: `esWriter_queue`)
  - `ESWRITER_BULK_CHUNK` (по умолчанию: `2000`)

## Сборка и запуск
```
cd microservices/PolygonDataGen
docker build -t polygon-data-gen .
# или
docker compose up -d --build
```

Compose ожидает внешнюю Docker-сеть `app-network` и файл `.env` с указанными выше переменными окружения.

## Сигнатура задачи
Имя задачи: `polygons.generate_data` (настраивается через переменные окружения). Сервис генерирует документы и отправляет их пакетами в ESWriter. ESWriter всегда индексирует в алиас `way`.

Пример полезной нагрузки:
```json
{
  "index_name": "way",
  "mac_count": 100,
  "records_per_mac": [3000, 4000],
  "in_polygon_ratio": 0.2,
  "days_back": 30,
  "polygon_geojson": {
    "type": "Polygon",
    "coordinates": [[[37.6,55.72],[37.6,55.80],[37.75,55.80],[37.75,55.72],[37.6,55.72]]]
  },
  "tag": "polygons_gen_v1",
  "user_api": "<YOUR_API_KEY>",
  "seed": 42,
  "chunk_size": 5000
}
```

Вариант без полигона: передайте `polygon_bbox: [minx, miny, maxx, maxy]`.

## Постановка задачи (пример, из Django API)
```python
from celery import Celery
import os

BROKER_URL = os.getenv('CELERY_BROKER_URL')
celery_client = Celery('producer', broker=BROKER_URL)

cfg = {
  "index_name": "way",
  "mac_count": 100,
  "records_per_mac": [3000, 4000],
  "in_polygon_ratio": 0.2,
  "days_back": 30,
  "polygon_geojson": {"type": "Polygon", "coordinates": [[[37.6,55.72],[37.6,55.80],[37.75,55.80],[37.75,55.72],[37.6,55.72]]]},
  "user_api": "<YOUR_API_KEY>"
}
celery_client.send_task('polygons.generate_data', args=[cfg], queue='polygon_gen')
```

## Примечание по маппингу
Маппинг индекса задаётся ESWriter (см. его логику). Сгенерированные документы содержат поля, совместимые с UI/API проекта (`device_id`, `mac`, `user_phone_mac`, `location`, `latitude/longitude`, `network_type`, `detected_at` и т. д.).