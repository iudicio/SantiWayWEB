-- Query для детекции density anomalies
-- Использование: подставить {hours} параметр

WITH regional_stats AS (
    SELECT
        region,
        hour,
        unique_devices,
        avg(unique_devices) OVER w AS avg_devices,
        stddevPop(unique_devices) OVER w AS std_devices,
        quantile(0.95)(unique_devices) OVER w AS p95_devices
    FROM regional_density
    WHERE hour >= now() - INTERVAL {hours} HOUR
    WINDOW w AS (PARTITION BY region)
)
SELECT
    region,
    hour,
    unique_devices,
    avg_devices,
    p95_devices,
    -- Z-score
    (unique_devices - avg_devices) / nullIf(std_devices, 0) AS z_score,
    -- Relative anomaly score
    (unique_devices - p95_devices) / nullIf(p95_devices, 0) AS anomaly_score
FROM regional_stats
WHERE unique_devices > p95_devices
ORDER BY anomaly_score DESC
LIMIT 100;

