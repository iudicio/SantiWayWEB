USE anomaly_demo;

-- Hourly features (materialized view)
CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_features
ENGINE = AggregatingMergeTree()
ORDER BY (device_id, hour, region)
POPULATE
AS SELECT
    device_id,
    toStartOfHour(timestamp) AS hour,
    region,

    -- Event counts
    count() AS event_count,

    -- Activity metrics
    avg(activity_level) AS avg_activity,
    stddevPop(activity_level) AS std_activity,
    min(activity_level) AS min_activity,
    max(activity_level) AS max_activity,
    quantile(0.95)(activity_level) AS p95_activity,
    quantile(0.05)(activity_level) AS p05_activity,

    -- Spatial metrics
    avg(lat) AS avg_lat,
    avg(lon) AS avg_lon,
    stddevPop(lat) AS std_lat,
    stddevPop(lon) AS std_lon

FROM events
GROUP BY device_id, hour, region;

-- Regional density (materialized view)
CREATE MATERIALIZED VIEW IF NOT EXISTS regional_density
ENGINE = SummingMergeTree()
ORDER BY (region, hour)
POPULATE
AS SELECT
    region,
    toStartOfHour(timestamp) AS hour,

    count() AS total_events,
    uniq(device_id) AS unique_devices,

    avg(activity_level) AS avg_regional_activity,
    stddevPop(activity_level) AS std_regional_activity

FROM events
GROUP BY region, hour;

-- Daily aggregations (for long-term analysis)
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_features
ENGINE = SummingMergeTree()
ORDER BY (device_id, day)
POPULATE
AS SELECT
    device_id,
    toDate(timestamp) AS day,

    count() AS daily_event_count,
    avg(activity_level) AS daily_avg_activity,
    uniq(region) AS regions_visited,

    -- Movement indicators
    max(lat) - min(lat) AS lat_range,
    max(lon) - min(lon) AS lon_range

FROM events
GROUP BY device_id, day;

