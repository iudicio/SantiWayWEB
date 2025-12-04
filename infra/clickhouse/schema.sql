-- Создание базы данных
CREATE DATABASE IF NOT EXISTS santi;

-- Использование базы данных
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
