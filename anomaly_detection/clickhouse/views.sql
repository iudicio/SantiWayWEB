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

