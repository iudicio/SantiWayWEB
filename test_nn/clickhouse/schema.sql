-- Create database
CREATE DATABASE IF NOT EXISTS anomaly_demo;

USE anomaly_demo;

-- Events table (raw data)
CREATE TABLE IF NOT EXISTS events (
    timestamp DateTime64(3),
    device_id String,
    lat Float64,
    lon Float64,
    activity_level Float32,
    region String,
    event_date Date DEFAULT toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (device_id, timestamp)
TTL event_date + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- Anomalies table (results)
CREATE TABLE IF NOT EXISTS anomalies (
    detected_at DateTime DEFAULT now(),
    timestamp DateTime,
    device_id String,
    anomaly_type Enum8(
        'density_spike' = 1,
        'time_anomaly' = 2,
        'personal_deviation' = 3,
        'spatial_outlier' = 4
    ),
    anomaly_score Float32,
    region String,
    details String,
    event_date Date DEFAULT toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (anomaly_score, timestamp)
TTL event_date + INTERVAL 180 DAY;

-- Indexes for fast queries
ALTER TABLE anomalies ADD INDEX IF NOT EXISTS idx_device device_id TYPE bloom_filter GRANULARITY 1;
ALTER TABLE anomalies ADD INDEX IF NOT EXISTS idx_type anomaly_type TYPE set(0) GRANULARITY 1;

