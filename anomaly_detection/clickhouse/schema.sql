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

