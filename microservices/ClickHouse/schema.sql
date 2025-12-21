-- создаём БД
CREATE DATABASE IF NOT EXISTS santi;

USE santi;

-- Создание таблицы way_data
CREATE TABLE IF NOT EXISTS way_data
(
    -- Идентификаторы устройств
    device_id String COMMENT 'MAC-адрес устройства',
    user_phone_mac String COMMENT 'MAC-адрес телефона пользователя',

    -- Геолокация
    latitude Float64 COMMENT 'Широта',
    longitude Float64 COMMENT 'Долгота',

    -- Параметры сигнала
    signal_strength Int16 COMMENT 'Мощность сигнала (RSSI) в dBm',
    network_type String COMMENT 'Тип сети (wifi/bluetooth/gsm)',

    -- Флаги
    is_ignored UInt8 COMMENT 'Флаг игнорирования устройства (0/1)',
    is_alert UInt8 COMMENT 'Флаг тревоги (0/1)',

    -- Метаданные
    user_api String COMMENT 'API ключ пользователя',
    detected_at DateTime COMMENT 'Время обнаружения',
    folder_name String COMMENT 'Бизнес-название папки',
    system_folder_name String COMMENT 'Системное название папки',
    vendor String COMMENT 'Производитель устройства',

    -- Индексы для ускорения поиска (bloom filter для строковых полей)
    INDEX idx_device_id device_id TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX idx_user_api user_api TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX idx_vendor vendor TYPE bloom_filter(0.01) GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(detected_at)
ORDER BY (detected_at, device_id)
TTL detected_at + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;

-- Материализованное представление для агрегации по устройствам
CREATE MATERIALIZED VIEW IF NOT EXISTS way_data_device_stats
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (date, device_id, user_api)
AS SELECT
    toDate(detected_at) as date,
    device_id,
    user_api,
    vendor,
    network_type,
    count() as detection_count,
    avg(signal_strength) as avg_signal_strength,
    min(signal_strength) as min_signal_strength,
    max(signal_strength) as max_signal_strength
FROM way_data
GROUP BY date, device_id, user_api, vendor, network_type;

-- Материализованное представление для агрегации по папкам
CREATE MATERIALIZED VIEW IF NOT EXISTS way_data_folder_stats
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (date, folder_name, user_api)
AS SELECT
    toDate(detected_at) as date,
    folder_name,
    system_folder_name,
    user_api,
    count() as detection_count,
    uniq(device_id) as unique_devices
FROM way_data
GROUP BY date, folder_name, system_folder_name, user_api;


CREATE DATABASE IF NOT EXISTS anomaly_ml;

USE anomaly_ml;

CREATE TABLE IF NOT EXISTS anomalies (
    detected_at DateTime DEFAULT now() COMMENT 'Время детекции аномалии',
    timestamp DateTime COMMENT 'Время события',
    device_id String COMMENT 'MAC-адрес устройства',
    anomaly_type Enum8(
        'density_spike' = 1,
        'time_anomaly' = 2,
        'personal_deviation' = 3,
        'spatial_outlier' = 4,
        'night_activity' = 5,
        'following' = 6,
        'stationary_surveillance' = 7,
        'signal_anomaly' = 8
    ) COMMENT 'Тип аномалии',
    anomaly_score Float32 COMMENT 'Оценка аномальности (0-1)',
    folder_name String COMMENT 'Название папки где обнаружено',
    vendor String COMMENT 'Производитель устройства',
    network_type String COMMENT 'Тип сети',
    details String COMMENT 'Дополнительные детали в JSON',
    event_date Date DEFAULT toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (detected_at, anomaly_score, device_id)
TTL event_date + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

ALTER TABLE anomalies ADD INDEX IF NOT EXISTS idx_device device_id TYPE bloom_filter(0.01) GRANULARITY 1;
ALTER TABLE anomalies ADD INDEX IF NOT EXISTS idx_type anomaly_type TYPE set(0) GRANULARITY 1;
ALTER TABLE anomalies ADD INDEX IF NOT EXISTS idx_folder folder_name TYPE bloom_filter(0.01) GRANULARITY 1;
ALTER TABLE anomalies ADD INDEX IF NOT EXISTS idx_vendor vendor TYPE bloom_filter(0.01) GRANULARITY 1;

USE anomaly_ml;

CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_features
ENGINE = AggregatingMergeTree()
ORDER BY (device_id, hour, folder_name)
POPULATE
AS SELECT
    device_id,
    toStartOfHour(detected_at) AS hour,
    folder_name,
    vendor,
    network_type,

    count() AS event_count,

    avg(signal_strength) AS avg_signal,
    stddevPop(signal_strength) AS std_signal,
    min(signal_strength) AS min_signal,
    max(signal_strength) AS max_signal,
    quantile(0.95)(signal_strength) AS p95_signal,
    quantile(0.05)(signal_strength) AS p05_signal,

    avg(latitude) AS avg_lat,
    avg(longitude) AS avg_lon,
    stddevPop(latitude) AS std_lat,
    stddevPop(longitude) AS std_lon,

    sum(is_alert) AS alert_count,
    sum(is_ignored) AS ignored_count

FROM santi.way_data
WHERE is_ignored = 0 
GROUP BY device_id, hour, folder_name, vendor, network_type;

CREATE MATERIALIZED VIEW IF NOT EXISTS folder_density
ENGINE = SummingMergeTree()
ORDER BY (folder_name, hour)
POPULATE
AS SELECT
    folder_name,
    system_folder_name,
    toStartOfHour(detected_at) AS hour,

    count() AS total_events,
    uniq(device_id) AS unique_devices,
    uniq(vendor) AS unique_vendors,

    avg(signal_strength) AS avg_folder_signal,
    stddevPop(signal_strength) AS std_folder_signal,

    countIf(network_type = 'wifi') AS wifi_count,
    countIf(network_type = 'bluetooth') AS bluetooth_count,
    countIf(network_type = 'gsm') AS gsm_count

FROM santi.way_data
WHERE is_ignored = 0
GROUP BY folder_name, system_folder_name, hour;

CREATE MATERIALIZED VIEW IF NOT EXISTS daily_features
ENGINE = SummingMergeTree()
ORDER BY (device_id, day)
POPULATE
AS SELECT
    device_id,
    toDate(detected_at) AS day,
    anyLast(vendor) AS last_vendor,
    anyLast(folder_name) AS last_folder,

    count() AS daily_event_count,
    avg(signal_strength) AS daily_avg_signal,
    uniq(folder_name) AS folders_visited,

    max(latitude) - min(latitude) AS lat_range,
    max(longitude) - min(longitude) AS lon_range,

    uniq(network_type) AS network_types_used,

    countIf(toHour(detected_at) BETWEEN 0 AND 6) AS night_detections,
    countIf(toHour(detected_at) BETWEEN 7 AND 19) AS day_detections,
    countIf(toHour(detected_at) BETWEEN 20 AND 23) AS evening_detections

FROM santi.way_data
WHERE is_ignored = 0
GROUP BY device_id, day;

-- создаём пользователя
CREATE USER IF NOT EXISTS {{USER}}
IDENTIFIED BY {{PASSWORD}}
{{HOSTS}};

-- права
GRANT ALL ON santi.* TO {{USER}};
GRANT ALL ON anomaly_ml.* TO {{USER}};