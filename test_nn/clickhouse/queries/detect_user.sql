-- Query для детекции personal anomalies
-- Использование: подставить {device_id} и {hours}

WITH device_history AS (
    SELECT
        device_id,
        hour,
        event_count,
        avg_activity,
        std_activity,
        toHour(hour) AS hour_of_day,

        -- Historical baselines for this device and hour
        avg(event_count) OVER (
            PARTITION BY device_id, toHour(hour)
            ROWS BETWEEN 168 PRECEDING AND 1 PRECEDING  -- Last 7 days
        ) AS historical_avg_count,

        stddevPop(event_count) OVER (
            PARTITION BY device_id, toHour(hour)
            ROWS BETWEEN 168 PRECEDING AND 1 PRECEDING
        ) AS historical_std_count,

        avg(avg_activity) OVER (
            PARTITION BY device_id, toHour(hour)
            ROWS BETWEEN 168 PRECEDING AND 1 PRECEDING
        ) AS historical_avg_activity

    FROM hourly_features
    WHERE device_id = '{device_id}'
    AND hour >= now() - INTERVAL {hours} HOUR
)
SELECT
    device_id,
    hour,
    hour_of_day,
    event_count,
    historical_avg_count,
    avg_activity,
    historical_avg_activity,

    -- Deviation scores
    abs(event_count - historical_avg_count) / nullIf(historical_std_count, 1) AS count_z_score,
    abs(avg_activity - historical_avg_activity) / nullIf(historical_avg_activity, 1) AS activity_deviation

FROM device_history
WHERE count_z_score > 2.5  -- 2.5 sigma threshold
OR activity_deviation > 0.5  -- 50% deviation
ORDER BY count_z_score DESC
LIMIT 100;

