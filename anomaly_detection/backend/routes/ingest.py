from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List
from datetime import datetime
from backend.services.clickhouse_client import ch_client
from loguru import logger
import pandas as pd

router = APIRouter(prefix="/ingest", tags=["ingest"])

class Event(BaseModel):
    """Модель события устройства"""
    timestamp: datetime
    device_id: str
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    activity_level: float = Field(..., ge=0)
    region: str

class IngestResponse(BaseModel):
    status: str
    inserted: int
    message: str

@router.post("/events", response_model=IngestResponse)
async def insert_events(events: List[Event]):
    """
    Загрузка событий устройств в ClickHouse
    """

    try:
        data = [event.model_dump() for event in events]

        inserted = await ch_client.insert('events', data)

        logger.info(f"Inserted {inserted} events")

        return IngestResponse(
            status="success",
            inserted=inserted,
            message=f"Successfully inserted {inserted} events",
        )

    except Exception as e:
        logger.error(f"Insert failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/csv", response_model=IngestResponse)
async def insert_from_csv(file_path: str = "data/demo_events.csv"):
    """
    Загрузка событий из CSV файла
    """

    try:

        df = pd.read_csv(file_path)

        required_columns = ['timestamp', 'device_id', 'lat', 'lon', 'activity_level', 'region']
        df = df[[col for col in required_columns if col in df.columns]]

        data = df.to_dict('records')

        inserted = await ch_client.insert('events', data)

        logger.info(f"Inserted {inserted} events from CSV")

        return IngestResponse(
            status="success",
            inserted=inserted,
            message=f"Successfully inserted {inserted} events from {file_path}",
        )

    except Exception as e:
        logger.error(f"CSV insert failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
