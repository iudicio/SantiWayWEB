from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from backend.services.clickhouse_client import ch_client
from backend.services.anomaly_detector import AnomalyDetector
from backend.services.model_tcn import load_model
from backend.utils.config import settings
from loguru import logger

router = APIRouter(prefix="/analyze", tags=["analyze"])

model = None

def convert_anomaly_for_response(anomaly: Dict) -> Dict:
    """Convert anomaly dict to response format (datetime -> string)"""
    result = anomaly.copy()
    if isinstance(result.get('timestamp'), datetime):
        result['timestamp'] = result['timestamp'].isoformat()
    return result

class AnalyzeRequest(BaseModel):
    """Запрос на анализ"""
    period: str = Field(default="24h", description="Период анализа: 24h, 7d, 30d")
    detection_types: List[str] = Field(
        default=["density", "time", "personal"],
        description="Типы детекции: density, time, personal",
    )

class AnomalyResponse(BaseModel):
    """Модель аномалии"""
    timestamp: str
    device_id: Optional[str]
    anomaly_type: str
    anomaly_score: float
    region: Optional[str]
    details: Dict[str, Any]

class AnalyzeResponse(BaseModel):
    """Ответ анализа"""
    status: str
    period: str
    anomalies_found: int
    anomalies: List[AnomalyResponse]

def parse_period(period: str) -> int:
    """Конвертация периода в часы"""
    if period.endswith('h'):
        return int(period[:-1])
    elif period.endswith('d'):
        return int(period[:-1]) * 24
    elif period.endswith('w'):
        return int(period[:-1]) * 24 * 7
    else:
        return 24

@router.post("/global", response_model=AnalyzeResponse)
async def analyze_global(request: AnalyzeRequest):
    """
    Глобальный анализ всех устройств за период
    """

    try:
        hours = parse_period(request.period)

        detector = AnomalyDetector(ch_client, model)

        all_anomalies: List[Dict[str, Any]] = []

        if "density" in request.detection_types:
            density_anomalies = await detector.detect_density_anomalies(hours)
            all_anomalies.extend(density_anomalies)

        if "time" in request.detection_types:
            time_anomalies = await detector.detect_time_anomalies(hours)
            all_anomalies.extend(time_anomalies)

        if all_anomalies:
            await detector.save_anomalies(all_anomalies)

        logger.info(f"Global analysis completed: {len(all_anomalies)} anomalies")

        return AnalyzeResponse(
            status="completed",
            period=request.period,
            anomalies_found=len(all_anomalies),
            anomalies=[AnomalyResponse(**convert_anomaly_for_response(a)) for a in all_anomalies[:100]],
        )

    except Exception as e:
        logger.error(f"Global analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/device/{device_id}", response_model=AnalyzeResponse)
async def analyze_device(device_id: str, request: AnalyzeRequest):
    """
    Персональный анализ конкретного устройства
    """

    try:
        hours = parse_period(request.period)

        detector = AnomalyDetector(ch_client, model)

        personal_anomalies = await detector.detect_personal_anomalies(
            device_id, hours
        )

        if personal_anomalies:
            await detector.save_anomalies(personal_anomalies)

        logger.info(f"Device {device_id} analysis: {len(personal_anomalies)} anomalies")

        return AnalyzeResponse(
            status="completed",
            period=request.period,
            anomalies_found=len(personal_anomalies),
            anomalies=[AnomalyResponse(**convert_anomaly_for_response(a)) for a in personal_anomalies],
        )

    except Exception as e:
        logger.error(f"Device analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
