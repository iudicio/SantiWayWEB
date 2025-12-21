import numpy as np
import torch
import json
from typing import List, Dict, Any
from pathlib import Path
from backend.services.clickhouse_client import ClickHouseClient
from backend.services.feature_engineer import FeatureEngineer
from backend.services.model_tcn_advanced import TCN_Autoencoder_Advanced
from backend.services.data_validator import DataValidator
from backend.utils.config import settings
from loguru import logger

class AnomalyDetector:
    """Главный класс для детекции аномалий"""

    def __init__(
        self,
        ch_client: ClickHouseClient,
        model: TCN_Autoencoder_Advanced | None = None,
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

                is_valid, errors = DataValidator.validate_model_metadata(metadata)
                if not is_valid:
                    logger.warning(f"Model metadata validation issues: {errors}")

                if 'normalization' in metadata:
                    global_mean = np.array(metadata['normalization']['mean'])
                    global_std = np.array(metadata['normalization']['std'])
                    logger.info(f"Loaded global normalization stats for {len(global_mean)} features")
                    return global_mean, global_std
            except Exception as e:
                logger.warning(f"Failed to load normalization stats: {e}")
        return None, None

    def _load_model(self) -> TCN_Autoencoder_Advanced:
        """Загрузка Advanced модели с Multi-Head Attention"""

        metadata_path = Path('models/model_metadata.json')
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                input_channels = metadata.get('input_channels', settings.INPUT_CHANNELS)
                use_attention = metadata.get('use_attention', True)
            except Exception:
                input_channels = settings.INPUT_CHANNELS
                use_attention = True
        else:
            input_channels = settings.INPUT_CHANNELS
            use_attention = True

        model = TCN_Autoencoder_Advanced(
            input_channels=input_channels,
            hidden_channels=[128, 256, 512, 1024],  
            kernel_size=5,  
            dropout=0.3,
            use_attention=use_attention, 
            num_attention_heads=8,  
        )

        logger.info(
            f"Using ADVANCED TCN model: channels={[128,256,512,1024]}, "
            f"attention={'ON' if use_attention else 'OFF'}, input_features={input_channels}"
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
        """Детект аномалий плотности (скопления устройств) по папкам

        Защита от SQL Injection через parameterized queries
        """

        query = """
        WITH folder_stats AS (
            SELECT
                folder_name,
                system_folder_name,
                hour,
                unique_devices,
                unique_vendors,
                quantile(0.95)(unique_devices) OVER (PARTITION BY folder_name) AS p95_devices
            FROM anomaly_ml.folder_density
            WHERE hour >= now() - INTERVAL %s HOUR
        )
        SELECT
            folder_name,
            system_folder_name,
            hour,
            unique_devices,
            unique_vendors,
            p95_devices,
            (unique_devices - p95_devices) / nullIf(p95_devices, 0) AS anomaly_score
        FROM folder_stats
        WHERE unique_devices > p95_devices
        ORDER BY anomaly_score DESC
        LIMIT 100
        """

        result = await self.ch.query(query, [hours])

        anomalies = []
        for row in result:
            anomalies.append({
                'timestamp': row['hour'],
                'device_id': '',
                'anomaly_type': 'density_spike',
                'anomaly_score': float(row['anomaly_score']),
                'folder_name': row['folder_name'],
                'vendor': '',
                'network_type': '',
                'details': {
                    'unique_devices': int(row['unique_devices']),
                    'unique_vendors': int(row['unique_vendors']),
                    'p95_baseline': float(row['p95_devices']),
                    'folder': row['system_folder_name'],
                },
            })

        logger.info(f"Density anomalies detected: {len(anomalies)}")
        return anomalies

    async def detect_time_anomalies(self, hours: int = 24) -> List[Dict]:
        """Детект временных аномалий (активность в необычное время) с использованием signal strength

        Защита от SQL Injection через parameterized queries
        """

        query = """
        WITH hourly_stats AS (
            SELECT
                device_id,
                hour,
                folder_name,
                vendor,
                network_type,
                toHour(hour) AS hour_of_day,
                event_count,
                avg_signal,
                avg(event_count) OVER (
                    PARTITION BY device_id, toHour(hour)
                ) AS avg_count_for_hour,
                stddevPop(event_count) OVER (
                    PARTITION BY device_id, toHour(hour)
                ) AS std_count_for_hour
            FROM anomaly_ml.hourly_features
            WHERE hour >= now() - INTERVAL %s HOUR
        )
        SELECT
            device_id,
            hour,
            folder_name,
            vendor,
            network_type,
            hour_of_day,
            event_count,
            avg_signal,
            avg_count_for_hour,
            std_count_for_hour,
            abs(event_count - avg_count_for_hour) / nullIf(std_count_for_hour, 0) AS z_score
        FROM hourly_stats
        WHERE z_score > 3
        AND (hour_of_day < 6 OR hour_of_day > 23)
        ORDER BY z_score DESC
        LIMIT 100
        """

        result = await self.ch.query(query, [hours])

        anomalies = []
        for row in result:
            anomalies.append({
                'timestamp': row['hour'],
                'device_id': row['device_id'],
                'anomaly_type': 'time_anomaly',
                'anomaly_score': float(row['z_score']),
                'folder_name': row['folder_name'],
                'vendor': row['vendor'],
                'network_type': row['network_type'],
                'details': {
                    'event_count': int(row['event_count']),
                    'avg_signal': float(row['avg_signal']),
                    'avg_baseline': float(row['avg_count_for_hour']),
                    'hour_of_day': int(row['hour_of_day']),
                },
            })

        logger.info(f"Time anomalies detected: {len(anomalies)}")
        return anomalies

    async def detect_stationary_anomalies(self, hours: int = 24) -> List[Dict]:
        """Детект стационарного наблюдения (устройство долго на месте с сильным сигналом)

        Защита от SQL Injection через parameterized queries
        """

        query = """
        SELECT
            device_id,
            hour,
            folder_name,
            vendor,
            network_type,
            event_count,
            avg_signal,
            std_lat,
            std_lon,
            (std_lat + std_lon) AS movement_score
        FROM anomaly_ml.hourly_features
        WHERE hour >= now() - INTERVAL %s HOUR
        AND event_count > 10
        AND (std_lat + std_lon) < 0.001
        AND abs(avg_signal) > 50
        ORDER BY abs(avg_signal) DESC
        LIMIT 100
        """

        result = await self.ch.query(query, [hours])

        anomalies = []
        for row in result:
            signal_strength = abs(float(row['avg_signal']))
            score = signal_strength / 100.0 * (1 - float(row['movement_score']) * 1000)
            anomalies.append({
                'timestamp': row['hour'],
                'device_id': row['device_id'],
                'anomaly_type': 'stationary_surveillance',
                'anomaly_score': max(0, min(1, score)),
                'folder_name': row['folder_name'],
                'vendor': row['vendor'],
                'network_type': row['network_type'],
                'details': {
                    'event_count': int(row['event_count']),
                    'avg_signal': float(row['avg_signal']),
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
            logger.warning(f"Not enough data for device {device_id}: {len(df)} rows (need >= {settings.WINDOW_SIZE})")
            return []

        is_valid, errors = DataValidator.validate_dataframe(df)
        if not is_valid:
            logger.warning(f"Data validation failed for device {device_id}: {errors}")

        timeseries = self.feature_engineer.prepare_timeseries(
            df, settings.WINDOW_SIZE
        )

        if len(timeseries) == 0:
            logger.warning(f"No valid time windows for device {device_id}")
            return []

        is_valid, errors = DataValidator.validate_features(timeseries, expected_features=98)
        if not is_valid:
            logger.error(f"Feature validation failed for device {device_id}: {errors}")
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
            row = df.iloc[timestamp_idx]

            anomalies.append({
                'timestamp': row['hour'],
                'device_id': device_id,
                'anomaly_type': anomaly_type,
                'anomaly_score': float(scores[idx]),
                'folder_name': row.get('folder_name', ''),
                'vendor': row.get('vendor', ''),
                'network_type': row.get('network_type', ''),
                'details': {
                    'reconstruction_error': float(scores[idx]),
                    'threshold': threshold,
                },
            })

        logger.info(f"Personal anomalies for {device_id}: {len(anomalies)}")
        return anomalies

    def _classify_anomaly_type(self, df, idx: int, score: float) -> str:
        """Классификация типа аномалии по признакам (на основе signal strength)"""

        row = df.iloc[idx]

        try:
            hour_of_day = int(row.get('hour_of_day', 12))
        except (TypeError, ValueError):
            hour_of_day = 12

        std_lat = float(row.get('std_lat', 0))
        std_lon = float(row.get('std_lon', 0))
        event_count = int(row.get('event_count', 0))
        avg_signal = abs(float(row.get('avg_signal', 0)))

        movement = std_lat + std_lon

        if 0 <= hour_of_day <= 6 and avg_signal > 40:
            return 'night_activity'

        if movement < 0.001 and avg_signal > 50 and event_count > 5:
            return 'stationary_surveillance'

        if movement < 0.005 and avg_signal > 30:
            return 'following'

        if score > 0.5:
            return 'personal_deviation'

        return 'personal_deviation'

    async def save_anomalies(self, anomalies: List[Dict]) -> int:
        """Сохранение аномалий в таблицу с поддержкой production полей"""

        if not anomalies:
            return 0

        rows: List[Dict[str, Any]] = []
        for a in anomalies:
            rows.append({
                'timestamp': a['timestamp'],
                'device_id': a.get('device_id', ''),
                'anomaly_type': a['anomaly_type'],
                'anomaly_score': a['anomaly_score'],
                'folder_name': a.get('folder_name', ''),
                'vendor': a.get('vendor', ''),
                'network_type': a.get('network_type', ''),
                'details': str(a.get('details', {})),
            })

        return await self.ch.insert('anomaly_ml.anomalies', rows)

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
