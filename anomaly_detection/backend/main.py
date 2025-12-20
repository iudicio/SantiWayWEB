from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import sys
import time
import uvicorn
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import json
from pathlib import Path

from backend.services.clickhouse_client import ch_client
from backend.services.model_manager import ModelManager
from backend.services.websocket_notification_service import get_websocket_notification_service
from backend.services.metrics import (
    MetricsCollector,
    get_metrics,
    get_metrics_content_type
)
from backend.utils.config import settings
from backend.routes import ingest, analyze, anomalies, comparison, explain

logger.remove()
logger.add(sys.stdout, level="INFO")

limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management: startup and shutdown"""

    logger.info("Starting Anomaly Detection API...")

    await ch_client.connect()

    logger.info("Initializing ClickHouse schema...")
    await ch_client.initialize_schema()

    manager = ModelManager(settings.MODEL_PATH, settings.DEVICE)
    model = manager.load()

    app.state.model = model
    analyze.model = model

    metadata_path = Path('models/model_metadata.json')
    if metadata_path.exists():
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
            MetricsCollector.set_model_info(
                model_type='TCN_Autoencoder',
                input_channels=metadata.get('input_channels', settings.INPUT_CHANNELS),
                threshold_95=metadata.get('thresholds', {}).get('95', settings.ANOMALY_THRESHOLD_95),
                threshold_99=metadata.get('thresholds', {}).get('99', settings.ANOMALY_THRESHOLD_99)
            )

    logger.info("Starting WebSocket notification service...")
    notification_service = get_websocket_notification_service()
    await notification_service.start()

    logger.info("API ready!")

    yield

    logger.info("Shutting down...")
    await notification_service.stop()
    await ch_client.disconnect()

app = FastAPI(
    title="Anomaly Detection API",
    description="Demo API for device activity anomaly detection",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

allowed_origins_list = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info(f"CORS allowed origins: {allowed_origins_list}")

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    MetricsCollector.record_request(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code,
        duration=duration
    )

    return response

app.include_router(ingest.router)
app.include_router(analyze.router)
app.include_router(anomalies.router)
app.include_router(comparison.router)
app.include_router(explain.router)

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "healthy",
        "service": "Anomaly Detection API",
        "version": "1.0.0",
    }

@app.get("/health")
async def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "clickhouse": "connected",
        "model_loaded": hasattr(app.state, 'model'),
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=get_metrics(),
        media_type=get_metrics_content_type()
    )

if __name__ == "__main__":

    uvicorn.run(
        "backend.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
    )
