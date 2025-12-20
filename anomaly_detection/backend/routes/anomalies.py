from fastapi import APIRouter, Query, HTTPException, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from backend.services.clickhouse_client import ch_client
from backend.services.anomaly_detector import AnomalyDetector
from backend.services.websocket_notification_service import notify_anomalies_for_user_ws
from backend.services.feature_engineer import FeatureEngineer
from backend.services.data_validator import DataValidator
from loguru import logger
from pathlib import Path
import json
from slowapi import Limiter
from slowapi.util import get_remote_address
from backend.utils.config import settings

router = APIRouter(prefix="/anomalies", tags=["anomalies"])

limiter = Limiter(key_func=get_remote_address)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def validate_api_key(api_key: Optional[str]) -> bool:
    """
    Валидация API ключа из HTTP Header

    Args:
        api_key: API ключ для проверки (из X-API-Key header)

    Returns:
        bool: True если ключ валидный или валидация отключена

    Raises:
        HTTPException: 401 если ключ невалидный или отсутствует
    """
    if not settings.VALID_API_KEYS:
        logger.warning("API key validation is disabled (dev mode)")
        return True

    if not api_key:
        logger.warning("Missing API key in X-API-Key header")
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide X-API-Key header."
        )

    valid_keys = [k.strip() for k in settings.VALID_API_KEYS.split(",") if k.strip()]

    if api_key not in valid_keys:
        logger.warning(f"Invalid API key attempt: {api_key[:8]}...")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key. Access denied."
        )

    return True

class AnomalyRecord(BaseModel):
    """Запись аномалии из БД"""
    detected_at: datetime
    timestamp: datetime
    device_id: Optional[str]
    anomaly_type: Optional[str]
    anomaly_score: float
    region: Optional[str]
    details: str

class AnomaliesResponse(BaseModel):
    """Список аномалий"""
    total: int
    anomalies: List[AnomalyRecord]

@router.get("", response_model=AnomaliesResponse)
@limiter.limit("100/minute")
async def get_anomalies(
    request: Request,
    limit: int = Query(default=100, le=1000),
    anomaly_type: Optional[str] = None,
    min_score: float = Query(default=0.0, ge=0.0),
    device_id: Optional[str] = None,
):
    """
    Получение списка обнаруженных аномалий
    Защита от SQL Injection через parameterized queries
    Rate limit: 100 requests per minute
    """

    try:
        filters = ["anomaly_score >= %s"]
        params = [min_score]

        if anomaly_type:
            filters.append("anomaly_type = %s")
            params.append(anomaly_type)

        if device_id:
            filters.append("device_id = %s")
            params.append(device_id)

        where_clause = " AND ".join(filters)

        query = f"""
        SELECT
            detected_at,
            timestamp,
            device_id,
            anomaly_type,
            anomaly_score,
            region,
            details
        FROM anomalies
        WHERE {where_clause}
        ORDER BY anomaly_score DESC, detected_at DESC
        LIMIT %s
        """

        query_params = params + [limit]
        result = await ch_client.query(query, query_params)

        count_query = f"""
        SELECT count() as total
        FROM anomalies
        WHERE {where_clause}
        """

        count_result = await ch_client.query(count_query, params)
        total = count_result[0]['total'] if count_result else 0

        logger.info(f"Retrieved {len(result)} anomalies (total: {total})")

        return AnomaliesResponse(
            total=total,
            anomalies=[AnomalyRecord(**r) for r in result],
        )

    except Exception as e:
        logger.error(f"Get anomalies failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_anomaly_stats():
    """
    Статистика по аномалиям
    """

    try:
        query = """
        SELECT
            anomaly_type,
            count() as count,
            avg(anomaly_score) as avg_score,
            max(anomaly_score) as max_score
        FROM anomalies
        WHERE detected_at >= now() - INTERVAL 24 HOUR
        GROUP BY anomaly_type
        ORDER BY count DESC
        """

        result = await ch_client.query(query)

        return {
            "period": "last_24h",
            "stats": result,
        }

    except Exception as e:
        logger.error(f"Get stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/detect-and-notify")
@limiter.limit("10/minute")
async def detect_and_notify_anomalies(
    request: Request,
    hours: int = Query(default=24, ge=1, le=168, description="Количество часов для анализа"),
    api_key: Optional[str] = api_key_header,
):
    """
    Запуск детекции аномалий и отправка через WebSocket

    Rate limit: 10 requests per minute (resource intensive operation)

    Этот endpoint:
    1. Валидирует API key из HTTP Header (X-API-Key)
    2. Запускает все детекторы аномалий (density, time, stationary)
    3. Сохраняет аномалии в БД
    4. Отправляет уведомления через WebSocket подключенным клиентам

    Требования:
    - HTTP Header: X-API-Key: <your-api-key>
    - WebSocket подключение: ws://host/ws/notifications/?api_key={api_key}

    Security:
    - API key передается через HTTP Header (не попадает в URL/логи)
    - Поддержка dev mode (если VALID_API_KEYS пусто)
    """
    try:
        validate_api_key(api_key)

        logger.info(f"Starting anomaly detection for api_key={api_key[-6:]}... (last {hours}h)")

        detector = AnomalyDetector(ch_client)

        all_anomalies = await detector.detect_all_anomalies(hours=hours)

        if not all_anomalies:
            logger.info("No anomalies detected")
            return {
                "status": "success",
                "detected": 0,
                "saved": 0,
                "notified": 0,
                "message": "No anomalies detected in the specified period"
            }

        saved_count = await detector.save_anomalies(all_anomalies)
        logger.info(f"Saved {saved_count} anomalies to database")

        notified_count = await notify_anomalies_for_user_ws(api_key, all_anomalies)
        logger.info(f"Sent {notified_count} notifications via WebSocket")

        types_stats = {}
        for anomaly in all_anomalies:
            atype = anomaly.get('anomaly_type', 'unknown')
            types_stats[atype] = types_stats.get(atype, 0) + 1

        return {
            "status": "success",
            "detected": len(all_anomalies),
            "saved": saved_count,
            "notified": notified_count,
            "types": types_stats,
            "top_anomalies": [
                {
                    "type": a.get('anomaly_type'),
                    "device_id": a.get('device_id', '')[:12] + '...' if a.get('device_id') else '',
                    "score": round(a.get('anomaly_score', 0), 3),
                    "folder": a.get('folder_name', ''),
                }
                for a in sorted(all_anomalies, key=lambda x: x.get('anomaly_score', 0), reverse=True)[:5]
            ]
        }

    except Exception as e:
        logger.error(f"Detection and notification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """
    Проверка состояния ML системы и качества данных

    Возвращает:
    - Статус модели (загружена, количество признаков, версия)
    - Валидация метаданных модели
    - Качество production данных (последние 24 часа)
    - Доступность ClickHouse
    """
    health_status = {
        "status": "unknown",
        "model": {},
        "data": {},
        "clickhouse": {},
        "issues": []
    }

    try:
        model_path = Path('models/tcn_model.pt')
        metadata_path = Path('models/model_metadata.json')

        health_status["model"]["model_file_exists"] = model_path.exists()
        health_status["model"]["metadata_exists"] = metadata_path.exists()

        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            health_status["model"]["input_channels"] = metadata.get('input_channels')
            health_status["model"]["window_size"] = metadata.get('window_size')
            health_status["model"]["data_source"] = metadata.get('data_source')
            health_status["model"]["thresholds"] = metadata.get('thresholds')

            is_valid, errors = DataValidator.validate_model_metadata(metadata)
            health_status["model"]["metadata_valid"] = is_valid
            if not is_valid:
                health_status["issues"].extend([f"Model: {err}" for err in errors])

            if metadata.get('data_source') != 'production_way_data':
                health_status["issues"].append(
                    f"Model trained on '{metadata.get('data_source')}', not production data"
                )

            if metadata.get('input_channels') != 98:
                health_status["issues"].append(
                    f"Model has {metadata.get('input_channels')} features, expected 98"
                )
        else:
            health_status["issues"].append("Model metadata file not found")


        try:
            fe = FeatureEngineer(ch_client)
            df = await fe.get_hourly_features(device_id=None, hours=24)

            report = DataValidator.get_data_quality_report(df)
            health_status["data"] = report

            is_valid, errors = DataValidator.validate_dataframe(df)
            health_status["data"]["valid"] = is_valid
            if not is_valid:
                health_status["issues"].extend([f"Data: {err}" for err in errors])

            if report.get("rows", 0) == 0:
                health_status["issues"].append("No data in last 24 hours")
            elif report.get("rows", 0) < 100:
                health_status["issues"].append(f"Low data volume: only {report['rows']} rows in 24h")

            health_status["clickhouse"]["status"] = "connected"
            health_status["clickhouse"]["available"] = True

        except Exception as e:
            health_status["clickhouse"]["status"] = "error"
            health_status["clickhouse"]["error"] = str(e)
            health_status["clickhouse"]["available"] = False
            health_status["issues"].append(f"ClickHouse: {str(e)}")

        if len(health_status["issues"]) == 0:
            health_status["status"] = "healthy"
        elif health_status["clickhouse"]["available"] and health_status["model"]["model_file_exists"]:
            health_status["status"] = "degraded"
        else:
            health_status["status"] = "unhealthy"

        return health_status

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        health_status["status"] = "error"
        health_status["issues"].append(f"Health check error: {str(e)}")
        return health_status
