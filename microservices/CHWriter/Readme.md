# CHWriter Microservice

Микросервис для записи данных устройств в ClickHouse.

## Описание

CHWriter - это Celery worker, который:
- Слушает очередь `chWriter_queue`
- Получает обработанные данные от Vendor микросервиса
- Записывает данные батчами в ClickHouse (таблица `way_data`)

## Архитектура

Данные теперь поступают **параллельно** в Elasticsearch и ClickHouse:

```
                    ┌→ ESWriter → Elasticsearch
API → Vendor → ────┤
                    └→ CHWriter → ClickHouse
```

### Особенности реализации

#### Параллельность
- Данные отправляются **одновременно** в ES и CH
- Используются независимые Celery очереди
- Сбой в одной системе НЕ влияет на другую

#### Батчинг
- CHWriter обрабатывает документы батчами по 2000
- Оптимизация производительности вставки

#### Обработка ошибок
- Ошибки логируются, но не останавливают обработку
- Возвращается статистика: количество вставленных и ошибочных документов

## Конфигурация

Настройки через переменные окружения (см. `.env.example`):

### Celery
- `CELERY_BROKER_URL` - URL RabbitMQ брокера
- `CELERY_C_TASK_NAME` - имя задачи (по умолчанию: `chWriter`)
- `CELERY_C_QUEUE_NAME` - имя очереди (по умолчанию: `chWriter_queue`)
- `CELERY_LOG_LEVEL` - уровень логирования

### ClickHouse
- `CLICKHOUSE_HOST` - хост ClickHouse (по умолчанию: `clickhouse`)
- `CLICKHOUSE_PORT` - порт HTTP интерфейса (по умолчанию: `8123`)
- `CLICKHOUSE_USER` - пользователь (по умолчанию: `default`)
- `CLICKHOUSE_PASSWORD` - пароль
- `CLICKHOUSE_DATABASE` - база данных (по умолчанию: `santi`)
- `CLICKHOUSE_TABLE` - таблица (по умолчанию: `way_data`)

## Запуск

### Docker
```bash
docker-compose up chwriter
```

### Локально (для разработки)
```bash
export $(cat .env | xargs)
celery -A celery_app worker -Q chWriter_queue -n chWriter -c 1 -l INFO
```

## Структура данных

Микросервис ожидает список документов в формате:

```python
{
    "device_id": "AA:BB:CC:DD:EE:FF",
    "user_phone_mac": "XX:YY:ZZ:AA:BB:CC",
    "latitude": 55.75,
    "longitude": 37.62,
    "signal_strength": -67,
    "network_type": "wifi",
    "is_ignored": false,
    "is_alert": false,
    "user_api": "api_123",
    "detected_at": "2025-12-04T10:30:00Z",
    "folder_name": "Moscow",
    "system_folder_name": "msk",
    "vendor": "Apple Inc."
}
```

## Схема БД ClickHouse

### Структура таблицы `way_data`

- `device_id` (String) - MAC-адрес устройства
- `user_phone_mac` (String) - MAC-адрес телефона пользователя
- `latitude` (Float64) - широта
- `longitude` (Float64) - долгота
- `signal_strength` (Int16) - мощность сигнала RSSI
- `network_type` (String) - тип сети (wifi/bluetooth/gsm)
- `is_ignored` (UInt8) - флаг игнорирования
- `is_alert` (UInt8) - флаг тревоги
- `user_api` (String) - API ключ
- `detected_at` (DateTime) - время обнаружения
- `folder_name` (String) - бизнес-название папки
- `system_folder_name` (String) - системное название папки
- `vendor` (String) - производитель устройства

### Особенности таблицы

- Engine: `MergeTree()`
- Партиционирование: по месяцам (`toYYYYMM(detected_at)`)
- Сортировка: `(detected_at, device_id)`
- TTL: 365 дней
- Индексы: bloom_filter на `device_id`, `user_api`, `vendor`

### Материализованные представления

- `way_data_device_stats` - статистика по устройствам
- `way_data_folder_stats` - статистика по папкам

## Примеры запросов

### Количество устройств по дням
```sql
SELECT
    toDate(detected_at) as date,
    count() as detections,
    uniq(device_id) as unique_devices
FROM way_data
GROUP BY date
ORDER BY date DESC
LIMIT 30;
```

### Топ производителей устройств
```sql
SELECT
    vendor,
    count() as count,
    avg(signal_strength) as avg_signal
FROM way_data
WHERE detected_at >= today() - 7
GROUP BY vendor
ORDER BY count DESC
LIMIT 10;
```

### Статистика по папкам (из материализованного представления)
```sql
SELECT * FROM way_data_folder_stats
WHERE date = today()
ORDER BY detection_count DESC;
```

## Мониторинг

### Очереди RabbitMQ
```bash
# Посмотреть очередь CHWriter
docker exec santi_rabbitmq rabbitmqctl list_queues name messages consumers
```

### Логи CHWriter
```bash
docker-compose logs -f chwriter
```

### Логи Vendor (отправка в обе системы)
```bash
docker-compose logs -f vendor
```

### Проверить данные в ClickHouse
```bash
# Войти в ClickHouse CLI
docker exec -it santi_clickhouse clickhouse-client

# Выполнить запросы
USE santi;
SELECT count() FROM way_data;
SELECT * FROM way_data LIMIT 10;
```

## Troubleshooting

### CHWriter не подключается к ClickHouse
```bash
# Проверить healthcheck
docker-compose ps clickhouse

# Проверить сеть
docker exec santi_chwriter ping -c 3 clickhouse
```

### Данные не попадают в ClickHouse
```bash
# Проверить очередь
docker exec santi_rabbitmq rabbitmqctl list_queues | grep chWriter

# Проверить логи Vendor (отправка)
docker-compose logs vendor | grep chWriter

# Проверить логи CHWriter (получение)
docker-compose logs chwriter
```


