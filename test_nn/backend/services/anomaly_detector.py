import numpy as np
import torch
import json
from typing import List, Dict, Any
from pathlib import Path
from backend.services.clickhouse_client import ClickHouseClient
from backend.services.feature_engineer import FeatureEngineer
from backend.services.model_tcn import TCN_Autoencoder
from backend.utils.config import settings
from loguru import logger

class AnomalyDetector:
    """Главный класс для детекции аномалий"""

    def __init__(
        self,
        ch_client: ClickHouseClient,
        model: TCN_Autoencoder | None = None,
    ):
        self.ch = ch_client
        self.device = settings.DEVICE

        global_mean, global_std = self._load_normalization_stats()
        self.feature_engineer = FeatureEngineer(ch_client, global_mean, global_std)

        if model is None:
            self.model = self._load_model()
        else:
            self.model = model

    def _load_normalization_stats(self):
        """Загрузка глобальных статистик нормализации"""
        metadata_path = Path('models/model_metadata.json')
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                if 'normalization' in metadata:
                    global_mean = np.array(metadata['normalization']['mean'])
                    global_std = np.array(metadata['normalization']['std'])
                    logger.info(f"Loaded global normalization stats for {len(global_mean)} features")
                    return global_mean, global_std
            except Exception as e:
                logger.warning(f"Failed to load normalization stats: {e}")
        return None, None

    def _load_model(self) -> TCN_Autoencoder:
        """Загрузка модели с правильным количеством признаков"""

        metadata_path = Path('models/model_metadata.json')
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                input_channels = metadata.get('input_channels', settings.INPUT_CHANNELS)
            except Exception:
                input_channels = settings.INPUT_CHANNELS
        else:
            input_channels = settings.INPUT_CHANNELS

        model = TCN_Autoencoder(
            input_channels=input_channels,
            hidden_channels=[64, 128, 256],
            kernel_size=3,
            dropout=0.2,
        )

        model_path = Path(settings.MODEL_PATH)
        if model_path.exists():
            try:
                checkpoint = torch.load(model_path, map_location=self.device)
                state_dict = (
                    checkpoint['model_state_dict']
                    if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint
                    else checkpoint
                )
                model.load_state_dict(state_dict)
                logger.info(f"Model loaded from {model_path} with {input_channels} features")
            except Exception as e:
                logger.warning(f"Failed to load model: {e}")
        else:
            logger.warning(f"Model not found at {model_path}")

        model.eval()
        return model.to(self.device)

    async def detect_density_anomalies(self, hours: int = 24) -> List[Dict]:
        """Детект аномалий плотности (скопления устройств)"""

        query = f"""
        WITH regional_stats AS (
            SELECT
                region,
                hour,
                unique_devices,
                quantile(0.95)(unique_devices) OVER (PARTITION BY region) AS p95_devices
            FROM regional_density
            WHERE hour >= now() - INTERVAL {hours} HOUR
        )
        SELECT
            region,
            hour,
            unique_devices,
            p95_devices,
            (unique_devices - p95_devices) / nullIf(p95_devices, 0) AS anomaly_score
        FROM regional_stats
        WHERE unique_devices > p95_devices
        ORDER BY anomaly_score DESC
        LIMIT 100
        """

        result = await self.ch.query(query)

        anomalies = []
        for row in result:
            anomalies.append({
                'timestamp': row['hour'],
                'device_id': '',
                'anomaly_type': 'density_spike',
                'anomaly_score': float(row['anomaly_score']),
                'region': row['region'],
                'details': {
                    'unique_devices': int(row['unique_devices']),
                    'p95_baseline': float(row['p95_devices']),
                },
            })

        logger.info(f"Density anomalies detected: {len(anomalies)}")
        return anomalies

    async def detect_time_anomalies(self, hours: int = 24) -> List[Dict]:
        """Детект временных аномалий (активность в необычное время)"""

        query = f"""
        WITH hourly_stats AS (
            SELECT
                device_id,
                hour,
                toHour(hour) AS hour_of_day,
                event_count,
                avg(event_count) OVER (
                    PARTITION BY device_id, toHour(hour)
                ) AS avg_count_for_hour,
                stddevPop(event_count) OVER (
                    PARTITION BY device_id, toHour(hour)
                ) AS std_count_for_hour
            FROM hourly_features
            WHERE hour >= now() - INTERVAL {hours} HOUR
        )
        SELECT
            device_id,
            hour,
            hour_of_day,
            event_count,
            avg_count_for_hour,
            std_count_for_hour,
            abs(event_count - avg_count_for_hour) / nullIf(std_count_for_hour, 0) AS z_score
        FROM hourly_stats
        WHERE z_score > 3
        AND (hour_of_day < 6 OR hour_of_day > 23)
        ORDER BY z_score DESC
        LIMIT 100
        """

        result = await self.ch.query(query)

        anomalies = []
        for row in result:
            anomalies.append({
                'timestamp': row['hour'],
                'device_id': row['device_id'],
                'anomaly_type': 'time_anomaly',
                'anomaly_score': float(row['z_score']),
                'region': '',
                'details': {
                    'event_count': int(row['event_count']),
                    'avg_baseline': float(row['avg_count_for_hour']),
                    'hour_of_day': int(row['hour_of_day']),
                },
            })

        logger.info(f"Time anomalies detected: {len(anomalies)}")
        return anomalies

    async def detect_stationary_anomalies(self, hours: int = 24) -> List[Dict]:
        """Детект стационарного наблюдения (устройство долго на месте с высокой активностью)"""

        query = f"""
        SELECT
            device_id,
            hour,
            region,
            event_count,
            avg_activity,
            std_lat,
            std_lon,
            (std_lat + std_lon) AS movement_score
        FROM hourly_features
        WHERE hour >= now() - INTERVAL {hours} HOUR
        AND event_count > 10
        AND (std_lat + std_lon) < 0.001
        AND avg_activity > 50
        ORDER BY avg_activity DESC
        LIMIT 100
        """

        result = await self.ch.query(query)

        anomalies = []
        for row in result:
            score = float(row['avg_activity']) / 100.0 * (1 - float(row['movement_score']) * 1000)
            anomalies.append({
                'timestamp': row['hour'],
                'device_id': row['device_id'],
                'anomaly_type': 'stationary_surveillance',
                'anomaly_score': max(0, min(1, score)),
                'region': row['region'],
                'details': {
                    'event_count': int(row['event_count']),
                    'avg_activity': float(row['avg_activity']),
                    'movement_score': float(row['movement_score']),
                },
            })

        logger.info(f"Stationary anomalies detected: {len(anomalies)}")
        return anomalies

    async def detect_personal_anomalies(
        self,
        device_id: str,
        hours: int = 168,
    ) -> List[Dict]:
        """Детект персональных аномалий для устройства с помощью ML модели"""

        df = await self.feature_engineer.get_hourly_features(device_id, hours)

        if df.empty or len(df) < settings.WINDOW_SIZE:
            return []

        timeseries = self.feature_engineer.prepare_timeseries(
            df, settings.WINDOW_SIZE
        )

        if len(timeseries) == 0:
            return []

        tensor = torch.FloatTensor(timeseries).permute(0, 2, 1).to(self.device)

        with torch.no_grad():
            scores = self.model.anomaly_score(tensor).cpu().numpy()

        threshold = settings.ANOMALY_THRESHOLD_99
        anomaly_indices = np.where(scores > threshold)[0]

        anomalies = []
        for idx in anomaly_indices:
            timestamp_idx = idx + settings.WINDOW_SIZE - 1

            anomaly_type = self._classify_anomaly_type(df, timestamp_idx, scores[idx])

            anomalies.append({
                'timestamp': df.iloc[timestamp_idx]['hour'],
                'device_id': device_id,
                'anomaly_type': anomaly_type,
                'anomaly_score': float(scores[idx]),
                'region': df.iloc[timestamp_idx]['region'],
                'details': {
                    'reconstruction_error': float(scores[idx]),
                    'threshold': threshold,
                },
            })

        logger.info(f"Personal anomalies for {device_id}: {len(anomalies)}")
        return anomalies

    def _classify_anomaly_type(self, df, idx: int, score: float) -> str:
        """Классификация типа аномалии по признакам"""

        row = df.iloc[idx]

        try:
            hour_of_day = int(row.get('hour_of_day', 12))
        except (TypeError, ValueError):
            hour_of_day = 12

        std_lat = float(row.get('std_lat', 0))
        std_lon = float(row.get('std_lon', 0))
        event_count = int(row.get('event_count', 0))
        avg_activity = float(row.get('avg_activity', 0))

        movement = std_lat + std_lon

        if 0 <= hour_of_day <= 6 and avg_activity > 40:
            return 'night_activity'

        if movement < 0.001 and avg_activity > 50 and event_count > 5:
            return 'stationary_surveillance'

        if movement < 0.005 and avg_activity > 30:
            return 'following'

        if score > 0.5:
            return 'personal_deviation'

        return 'personal_deviation'

    async def save_anomalies(self, anomalies: List[Dict]) -> int:
        """Сохранение аномалий в таблицу"""

        if not anomalies:
            return 0

        rows: List[Dict[str, Any]] = []
        for a in anomalies:
            rows.append({
                'timestamp': a['timestamp'],
                'device_id': a.get('device_id', ''),
                'anomaly_type': a['anomaly_type'],
                'anomaly_score': a['anomaly_score'],
                'region': a.get('region', ''),
                'details': str(a.get('details', {})),
            })

        return await self.ch.insert('anomalies', rows)

    async def detect_all_anomalies(self, hours: int = 24) -> List[Dict]:
        """Запуск всех детекторов"""

        all_anomalies = []

        density = await self.detect_density_anomalies(hours)
        all_anomalies.extend(density)

        time_anomalies = await self.detect_time_anomalies(hours)
        all_anomalies.extend(time_anomalies)

        stationary = await self.detect_stationary_anomalies(hours)
        all_anomalies.extend(stationary)

        all_anomalies.sort(key=lambda x: x['anomaly_score'], reverse=True)

        return all_anomalies
