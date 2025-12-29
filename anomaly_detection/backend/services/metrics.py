from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    multiprocess,
    REGISTRY
)
import time
from functools import wraps
from typing import Callable
from loguru import logger
import asyncio

REQUEST_COUNT = Counter(
    'anomaly_api_requests_total',
    'Total number of API requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'anomaly_api_request_latency_seconds',
    'Request latency in seconds',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

ANOMALIES_DETECTED = Counter(
    'anomaly_detections_total',
    'Total number of anomalies detected',
    ['anomaly_type']
)

DETECTION_LATENCY = Histogram(
    'anomaly_detection_latency_seconds',
    'Time to run anomaly detection',
    ['detection_type'],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

MODEL_INFERENCE_COUNT = Counter(
    'model_inference_total',
    'Total number of model inferences'
)

MODEL_INFERENCE_LATENCY = Histogram(
    'model_inference_latency_seconds',
    'Model inference latency',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
)

MODEL_ANOMALY_SCORES = Histogram(
    'model_anomaly_scores',
    'Distribution of anomaly scores',
    buckets=[0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0]
)

DB_QUERY_COUNT = Counter(
    'clickhouse_queries_total',
    'Total number of ClickHouse queries',
    ['query_type']
)

DB_QUERY_LATENCY = Histogram(
    'clickhouse_query_latency_seconds',
    'ClickHouse query latency',
    ['query_type'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

DB_INSERT_COUNT = Counter(
    'clickhouse_inserts_total',
    'Total number of rows inserted'
)

ACTIVE_DEVICES = Gauge(
    'active_devices_count',
    'Number of active devices in the system'
)

TOTAL_EVENTS = Gauge(
    'total_events_count',
    'Total number of events in database'
)

PENDING_ANOMALIES = Gauge(
    'pending_anomalies_count',
    'Number of unreviewed anomalies'
)

MODEL_INFO = Info(
    'anomaly_model',
    'Information about the loaded model'
)

class MetricsCollector:
    """Centralized metrics collection"""

    @staticmethod
    def record_request(method: str, endpoint: str, status: int, duration: float):
        """Record API request metrics"""
        REQUEST_COUNT.labels(
            method=method,
            endpoint=endpoint,
            status=str(status)
        ).inc()

        REQUEST_LATENCY.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)

    @staticmethod
    def record_anomaly_detected(anomaly_type: str, count: int = 1):
        """Record detected anomalies"""
        ANOMALIES_DETECTED.labels(anomaly_type=anomaly_type).inc(count)

    @staticmethod
    def record_detection_time(detection_type: str, duration: float):
        """Record anomaly detection latency"""
        DETECTION_LATENCY.labels(detection_type=detection_type).observe(duration)

    @staticmethod
    def record_inference(duration: float, scores: list = None):
        """Record model inference metrics"""
        MODEL_INFERENCE_COUNT.inc()
        MODEL_INFERENCE_LATENCY.observe(duration)

        if scores:
            for score in scores:
                MODEL_ANOMALY_SCORES.observe(score)

    @staticmethod
    def record_db_query(query_type: str, duration: float):
        """Record database query metrics"""
        DB_QUERY_COUNT.labels(query_type=query_type).inc()
        DB_QUERY_LATENCY.labels(query_type=query_type).observe(duration)

    @staticmethod
    def record_db_insert(count: int):
        """Record database insert count"""
        DB_INSERT_COUNT.inc(count)

    @staticmethod
    def update_system_metrics(active_devices: int, total_events: int, pending: int):
        """Update system gauge metrics"""
        ACTIVE_DEVICES.set(active_devices)
        TOTAL_EVENTS.set(total_events)
        PENDING_ANOMALIES.set(pending)

    @staticmethod
    def set_model_info(
        model_type: str,
        input_channels: int,
        threshold_95: float,
        threshold_99: float
    ):
        """Set model information"""
        MODEL_INFO.info({
            'model_type': model_type,
            'input_channels': str(input_channels),
            'threshold_95': str(threshold_95),
            'threshold_99': str(threshold_99)
        })

def track_time(metric_name: str = None):
    """Decorator to track function execution time"""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                if metric_name:
                    MetricsCollector.record_detection_time(metric_name, duration)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                if metric_name:
                    MetricsCollector.record_detection_time(metric_name, duration)

        if hasattr(func, '__wrapped__'):
            return async_wrapper

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator

def get_metrics() -> bytes:
    """Generate Prometheus metrics output"""
    return generate_latest(REGISTRY)

def get_metrics_content_type() -> str:
    """Get content type for metrics endpoint"""
    return CONTENT_TYPE_LATEST
