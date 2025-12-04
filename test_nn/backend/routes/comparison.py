from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from backend.services.clickhouse_client import ClickHouseClient
from backend.services.device_comparison import DeviceComparison
from loguru import logger

router = APIRouter(prefix="/comparison", tags=["comparison"])

class SimilarDevicesRequest(BaseModel):
    device_id: str
    hours: int = 168
    top_k: int = 10
    min_similarity: float = 0.8

class ClusterRequest(BaseModel):
    hours: int = 168
    eps: float = 0.3
    min_samples: int = 2

class CompareDevicesRequest(BaseModel):
    device_id_1: str
    device_id_2: str
    hours: int = 168

class CoordinatedRequest(BaseModel):
    hours: int = 24
    time_threshold_minutes: int = 5
    distance_threshold_km: float = 0.5

@router.post("/similar")
async def find_similar_devices(request: SimilarDevicesRequest):
    """Find devices with similar behavior patterns"""
    try:
        ch_client = ClickHouseClient()
        await ch_client.connect()

        comparison = DeviceComparison(ch_client)
        similar = await comparison.find_similar_devices(
            device_id=request.device_id,
            hours=request.hours,
            top_k=request.top_k,
            min_similarity=request.min_similarity
        )

        await ch_client.disconnect()

        return {
            "target_device": request.device_id,
            "similar_devices": similar,
            "count": len(similar)
        }

    except Exception as e:
        logger.error(f"Error finding similar devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clusters")
async def detect_clusters(request: ClusterRequest):
    """Detect behavioral clusters among devices"""
    try:
        ch_client = ClickHouseClient()
        await ch_client.connect()

        comparison = DeviceComparison(ch_client)
        result = await comparison.detect_behavioral_clusters(
            hours=request.hours,
            eps=request.eps,
            min_samples=request.min_samples
        )

        await ch_client.disconnect()

        return result

    except Exception as e:
        logger.error(f"Error detecting clusters: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/compare")
async def compare_devices(request: CompareDevicesRequest):
    """Compare two specific devices"""
    try:
        ch_client = ClickHouseClient()
        await ch_client.connect()

        comparison = DeviceComparison(ch_client)
        result = await comparison.compare_two_devices(
            device_id_1=request.device_id_1,
            device_id_2=request.device_id_2,
            hours=request.hours
        )

        await ch_client.disconnect()

        if 'error' in result:
            raise HTTPException(status_code=404, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/coordinated")
async def find_coordinated_devices(request: CoordinatedRequest):
    """Find potentially coordinated device pairs"""
    try:
        ch_client = ClickHouseClient()
        await ch_client.connect()

        comparison = DeviceComparison(ch_client)
        result = await comparison.find_coordinated_devices(
            hours=request.hours,
            time_threshold_minutes=request.time_threshold_minutes,
            distance_threshold_km=request.distance_threshold_km
        )

        await ch_client.disconnect()

        return {
            "coordinated_pairs": result,
            "count": len(result)
        }

    except Exception as e:
        logger.error(f"Error finding coordinated devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/profiles")
async def get_all_profiles(hours: int = 168, min_events: int = 50):
    """Get behavioral profiles for all devices"""
    try:
        ch_client = ClickHouseClient()
        await ch_client.connect()

        comparison = DeviceComparison(ch_client)
        profiles = await comparison.get_device_profiles(
            hours=hours,
            min_events=min_events
        )

        await ch_client.disconnect()

        profile_list = [
            {
                "device_id": device_id,
                "profile": profile.tolist()
            }
            for device_id, profile in profiles.items()
        ]

        return {
            "profiles": profile_list,
            "count": len(profile_list)
        }

    except Exception as e:
        logger.error(f"Error getting profiles: {e}")
        raise HTTPException(status_code=500, detail=str(e))
