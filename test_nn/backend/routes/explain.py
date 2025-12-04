from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import numpy as np
import torch
import json
from pathlib import Path
from backend.services.clickhouse_client import ClickHouseClient
from backend.services.feature_engineer import FeatureEngineer
from backend.services.explainer import AnomalyExplainer
from backend.services.model_manager import ModelManager
from backend.utils.config import settings
from loguru import logger

router = APIRouter(prefix="/explain", tags=["explain"])

def load_normalization_stats():
    """Загрузка глобальных статистик нормализации"""
    metadata_path = Path('models/model_metadata.json')
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            if 'normalization' in metadata:
                global_mean = np.array(metadata['normalization']['mean'])
                global_std = np.array(metadata['normalization']['std'])
                return global_mean, global_std
        except Exception as e:
            logger.warning(f"Failed to load normalization stats: {e}")
    return None, None

explainer = None

def get_explainer(model):
    """Get or create explainer instance"""
    global explainer
    if explainer is None:
        import json
        from pathlib import Path

        metadata_path = Path('models/model_metadata.json')
        input_channels = settings.INPUT_CHANNELS

        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
                input_channels = metadata.get('input_channels', settings.INPUT_CHANNELS)

        explainer = AnomalyExplainer(
            model=model,
            device=settings.DEVICE,
            input_channels=input_channels
        )

    return explainer

class ExplainRequest(BaseModel):
    device_id: str
    hours: int = 168
    top_k: int = 5

class ExplainAnomalyRequest(BaseModel):
    device_id: str
    timestamp: str
    top_k: int = 5

@router.post("/device")
async def explain_device_anomalies(request: ExplainRequest):
    """
    Explain anomalies detected for a specific device.
    Returns SHAP-based feature importance for each anomaly.
    """
    try:
        from backend.routes.analyze import model

        if model is None:
            raise HTTPException(status_code=503, detail="Model not loaded")

        ch_client = ClickHouseClient()
        await ch_client.connect()

        global_mean, global_std = load_normalization_stats()
        feature_engineer = FeatureEngineer(ch_client, global_mean, global_std)
        exp = get_explainer(model)

        df = await feature_engineer.get_hourly_features(
            request.device_id,
            request.hours
        )

        if df.empty or len(df) < settings.WINDOW_SIZE:
            await ch_client.disconnect()
            return {
                "device_id": request.device_id,
                "explanations": [],
                "message": "Insufficient data for analysis"
            }

        timeseries = feature_engineer.prepare_timeseries(
            df, settings.WINDOW_SIZE
        )

        if len(timeseries) == 0:
            await ch_client.disconnect()
            return {
                "device_id": request.device_id,
                "explanations": [],
                "message": "Could not prepare timeseries"
            }

        tensor = torch.FloatTensor(timeseries).permute(0, 2, 1).to(settings.DEVICE)

        with torch.no_grad():
            scores = model.anomaly_score(tensor).cpu().numpy()

        threshold = settings.ANOMALY_THRESHOLD_99
        anomaly_indices = np.where(scores > threshold)[0]

        if len(anomaly_indices) == 0:
            await ch_client.disconnect()
            return {
                "device_id": request.device_id,
                "explanations": [],
                "message": "No anomalies detected above threshold"
            }

        explanations = []
        for idx in anomaly_indices[:10]:
            timestamp_idx = idx + settings.WINDOW_SIZE - 1
            sample = timeseries[idx]

            try:
                explanation = exp.explain_anomaly(sample, request.top_k)
                explanations.append({
                    "timestamp": str(df.iloc[timestamp_idx]['hour']),
                    "anomaly_score": float(scores[idx]),
                    "explanation": explanation
                })
            except Exception as e:
                logger.warning(f"Failed to explain anomaly at {idx}: {e}")

        await ch_client.disconnect()

        return {
            "device_id": request.device_id,
            "total_anomalies": len(anomaly_indices),
            "explained": len(explanations),
            "explanations": explanations
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error explaining anomalies: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/features")
async def get_feature_descriptions():
    """Get descriptions of all features used in the model"""
    return {
        "basic_features": {
            "event_count": "Number of events in the time window",
            "avg_activity": "Average activity level (0-100)",
            "std_activity": "Standard deviation of activity",
            "avg_lat": "Average latitude position",
            "avg_lon": "Average longitude position",
            "hour": "Hour of day (0-23)"
        },
        "extended_features": {
            "min_activity": "Minimum activity level",
            "max_activity": "Maximum activity level",
            "activity_range": "Range between max and min activity",
            "p95_activity": "95th percentile of activity",
            "std_lat": "Movement variation in latitude",
            "std_lon": "Movement variation in longitude",
            "velocity": "Speed of movement (km/h)",
            "acceleration": "Change in speed",
            "bearing_change": "Direction changes",
            "location_entropy": "Diversity of visited locations",
            "stationarity_score": "How stationary the device is (0-1)",
            "hour_sin": "Time of day (sine component for cyclical encoding)",
            "hour_cos": "Time of day (cosine component for cyclical encoding)",
            "is_night": "Night time indicator (1 if 0-6 hours)"
        }
    }

@router.post("/compare-explanations")
async def compare_anomaly_explanations(device_ids: List[str], hours: int = 168):
    """
    Compare explanations across multiple devices.
    Useful for understanding common patterns.
    """
    try:
        from backend.routes.analyze import model

        if model is None:
            raise HTTPException(status_code=503, detail="Model not loaded")

        ch_client = ClickHouseClient()
        await ch_client.connect()

        global_mean, global_std = load_normalization_stats()
        feature_engineer = FeatureEngineer(ch_client, global_mean, global_std)
        exp = get_explainer(model)

        results = {}
        feature_importance_aggregate = {}

        for device_id in device_ids[:5]:
            df = await feature_engineer.get_hourly_features(device_id, hours)

            if df.empty or len(df) < settings.WINDOW_SIZE:
                results[device_id] = {"error": "Insufficient data"}
                continue

            timeseries = feature_engineer.prepare_timeseries(
                df, settings.WINDOW_SIZE
            )

            if len(timeseries) == 0:
                results[device_id] = {"error": "Could not prepare timeseries"}
                continue

            tensor = torch.FloatTensor(timeseries).permute(0, 2, 1).to(settings.DEVICE)

            with torch.no_grad():
                scores = model.anomaly_score(tensor).cpu().numpy()

            threshold = settings.ANOMALY_THRESHOLD_99
            anomaly_indices = np.where(scores > threshold)[0]

            if len(anomaly_indices) == 0:
                results[device_id] = {
                    "anomaly_count": 0,
                    "top_features": []
                }
                continue

            max_idx = anomaly_indices[np.argmax(scores[anomaly_indices])]
            sample = timeseries[max_idx]

            try:
                explanation = exp.explain_anomaly(sample, top_k=5)

                results[device_id] = {
                    "anomaly_count": len(anomaly_indices),
                    "max_score": float(scores[max_idx]),
                    "top_features": explanation['top_features']
                }

                for feat in explanation['top_features']:
                    name = feat['feature']
                    if name not in feature_importance_aggregate:
                        feature_importance_aggregate[name] = []
                    feature_importance_aggregate[name].append(feat['importance'])

            except Exception as e:
                results[device_id] = {"error": str(e)}

        await ch_client.disconnect()

        aggregate = {}
        for name, importances in feature_importance_aggregate.items():
            aggregate[name] = {
                "mean_importance": float(np.mean(importances)),
                "count": len(importances)
            }

        aggregate = dict(sorted(
            aggregate.items(),
            key=lambda x: x[1]['mean_importance'],
            reverse=True
        ))

        return {
            "device_results": results,
            "aggregate_importance": aggregate,
            "devices_analyzed": len(device_ids)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing explanations: {e}")
        raise HTTPException(status_code=500, detail=str(e))
