from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from backend.services.clickhouse_client import ch_client
from loguru import logger

router = APIRouter(prefix="/anomalies", tags=["anomalies"])

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
async def get_anomalies(
    limit: int = Query(default=100, le=1000),
    anomaly_type: Optional[str] = None,
    min_score: float = Query(default=0.0, ge=0.0),
    device_id: Optional[str] = None,
):
    """
    Получение списка обнаруженных аномалий
    """

    try:
        filters = [f"anomaly_score >= {min_score}"]

        if anomaly_type:
            filters.append(f"anomaly_type = '{anomaly_type}'")

        if device_id:
            filters.append(f"device_id = '{device_id}'")

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
        LIMIT {limit}
        """

        result = await ch_client.query(query)

        count_query = f"""
        SELECT count() as total
        FROM anomalies
        WHERE {where_clause}
        """

        count_result = await ch_client.query(count_query)
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
