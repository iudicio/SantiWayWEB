import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from loguru import logger
import asyncio
from backend.services.clickhouse_client import ClickHouseClient
from backend.services.feature_engineer import FeatureEngineer

class DataValidator:
    """Валидатор данных для ML pipeline"""

    REQUIRED_FIELDS = [
        'device_id', 'hour', 'folder_name', 'vendor', 'network_type',
        'event_count', 'avg_signal', 'std_signal', 'avg_lat', 'avg_lon',
        'std_lat', 'std_lon'
    ]

    SIGNAL_RANGE = (-100, 0) 
    LAT_RANGE = (-90, 90)
    LON_RANGE = (-180, 180)
    VALID_NETWORK_TYPES = {'wifi', 'bluetooth', 'gsm', 'unknown'}

    @staticmethod
    def validate_dataframe(df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Валидация DataFrame перед feature engineering

        Returns:
            (is_valid, errors): Tuple с флагом валидности и списком ошибок
        """
        errors = []

        if df.empty:
            errors.append("DataFrame is empty")
            return False, errors

        missing_fields = set(DataValidator.REQUIRED_FIELDS) - set(df.columns)
        if missing_fields:
            errors.append(f"Missing required fields: {missing_fields}")

        if 'event_count' in df.columns:
            if not pd.api.types.is_numeric_dtype(df['event_count']):
                errors.append("event_count must be numeric")
            elif (df['event_count'] < 0).any():
                errors.append("event_count contains negative values")

        if 'avg_signal' in df.columns:
            if not pd.api.types.is_numeric_dtype(df['avg_signal']):
                errors.append("avg_signal must be numeric")
            else:
                out_of_range = df[
                    (df['avg_signal'] < DataValidator.SIGNAL_RANGE[0]) |
                    (df['avg_signal'] > DataValidator.SIGNAL_RANGE[1])
                ]
                if len(out_of_range) > 0:
                    pct = len(out_of_range) / len(df) * 100
                    if pct > 10: 
                        errors.append(
                            f"avg_signal out of range ({DataValidator.SIGNAL_RANGE}): "
                            f"{pct:.1f}% of rows"
                        )

        if 'avg_lat' in df.columns and 'avg_lon' in df.columns:
            invalid_coords = df[
                (df['avg_lat'] < DataValidator.LAT_RANGE[0]) |
                (df['avg_lat'] > DataValidator.LAT_RANGE[1]) |
                (df['avg_lon'] < DataValidator.LON_RANGE[0]) |
                (df['avg_lon'] > DataValidator.LON_RANGE[1])
            ]
            if len(invalid_coords) > 0:
                pct = len(invalid_coords) / len(df) * 100
                if pct > 5: 
                    errors.append(f"Invalid coordinates: {pct:.1f}% of rows")

        if 'network_type' in df.columns:
            invalid_types = set(df['network_type'].unique()) - DataValidator.VALID_NETWORK_TYPES
            if invalid_types:
                errors.append(f"Invalid network_types: {invalid_types}")

        nan_pct = df.isnull().sum() / len(df) * 100
        high_nan_cols = nan_pct[nan_pct > 20].index.tolist()
        if high_nan_cols:
            errors.append(f"High NaN percentage (>20%) in columns: {high_nan_cols}")

        if 'hour' in df.columns:
            if not df['hour'].is_monotonic_increasing:
                logger.warning("DataFrame is not sorted by 'hour' - may affect feature computation")

        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def validate_features(features: np.ndarray, expected_features: int = 98) -> Tuple[bool, List[str]]:
        """
        Валидация вычисленных признаков перед inference

        Args:
            features: numpy array размерности (n_samples, window_size, n_features)
            expected_features: ожидаемое количество признаков (default: 98)

        Returns:
            (is_valid, errors): Tuple с флагом валидности и списком ошибок
        """
        errors = []

        if features.ndim != 3:
            errors.append(f"Features must be 3D array, got shape: {features.shape}")
            return False, errors

        n_samples, window_size, n_features = features.shape

        if n_features != expected_features:
            errors.append(
                f"Expected {expected_features} features, got {n_features}. "
                f"Model may fail during inference."
            )

        if np.isnan(features).any():
            nan_count = np.isnan(features).sum()
            nan_pct = nan_count / features.size * 100
            errors.append(f"Features contain {nan_count} NaN values ({nan_pct:.2f}%)")

        if np.isinf(features).any():
            inf_count = np.isinf(features).sum()
            errors.append(f"Features contain {inf_count} Inf values")

        if np.abs(features).max() > 100:
            errors.append(
                f"Extreme feature values detected (max abs: {np.abs(features).max():.2f}). "
                f"Check normalization."
            )

        feature_stds = features.reshape(-1, n_features).std(axis=0)
        zero_var_features = np.where(feature_stds < 1e-6)[0]
        if len(zero_var_features) > 5: 
            errors.append(
                f"{len(zero_var_features)} features have near-zero variance. "
                f"This may indicate data quality issues."
            )

        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def validate_model_metadata(metadata: Dict) -> Tuple[bool, List[str]]:
        """
        Валидация model_metadata.json

        Args:
            metadata: dict загруженный из model_metadata.json

        Returns:
            (is_valid, errors): Tuple с флагом валидности и списком ошибок
        """
        errors = []

        required_keys = ['input_channels', 'window_size', 'normalization', 'thresholds']
        missing_keys = set(required_keys) - set(metadata.keys())
        if missing_keys:
            errors.append(f"Missing required keys in metadata: {missing_keys}")

        if 'input_channels' in metadata:
            if metadata['input_channels'] != 98:
                errors.append(
                    f"Model trained on {metadata['input_channels']} features, "
                    f"expected 98. Retrain model on production data."
                )

        if 'normalization' in metadata:
            norm = metadata['normalization']
            if 'mean' not in norm or 'std' not in norm:
                errors.append("Normalization stats missing 'mean' or 'std'")
            elif len(norm['mean']) != metadata.get('input_channels', 0):
                errors.append(
                    f"Normalization mean length ({len(norm['mean'])}) "
                    f"doesn't match input_channels ({metadata.get('input_channels')})"
                )

        if metadata.get('data_source') != 'production_way_data':
            errors.append(
                f"Model trained on '{metadata.get('data_source')}', "
                f"not 'production_way_data'. Retrain on production data for best results."
            )

        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def get_data_quality_report(df: pd.DataFrame) -> Dict:
        """
        Генерация отчета о качестве данных

        Returns:
            Dict с метриками качества данных
        """
        if df.empty:
            return {"status": "empty", "rows": 0}

        report = {
            "status": "ok",
            "rows": len(df),
            "devices": df['device_id'].nunique() if 'device_id' in df.columns else 0,
            "time_range": {
                "start": str(df['hour'].min()) if 'hour' in df.columns else None,
                "end": str(df['hour'].max()) if 'hour' in df.columns else None,
            },
            "missing_values": df.isnull().sum().to_dict(),
            "field_stats": {}
        }

        if 'avg_signal' in df.columns:
            report['field_stats']['avg_signal'] = {
                "mean": float(df['avg_signal'].mean()),
                "std": float(df['avg_signal'].std()),
                "min": float(df['avg_signal'].min()),
                "max": float(df['avg_signal'].max()),
                "out_of_range_pct": float(
                    ((df['avg_signal'] < -100) | (df['avg_signal'] > 0)).sum() / len(df) * 100
                )
            }

        if 'event_count' in df.columns:
            report['field_stats']['event_count'] = {
                "mean": float(df['event_count'].mean()),
                "median": float(df['event_count'].median()),
                "max": int(df['event_count'].max()),
            }

        if 'network_type' in df.columns:
            report['field_stats']['network_types'] = df['network_type'].value_counts().to_dict()

        if 'vendor' in df.columns:
            report['field_stats']['top_vendors'] = (
                df['vendor'].value_counts().head(10).to_dict()
            )

        return report


if __name__ == "__main__":

    async def test_validation():
        ch = ClickHouseClient()
        await ch.connect()

        fe = FeatureEngineer(ch)
        df = await fe.get_hourly_features(device_id=None, hours=24)

        logger.info("=" * 60)
        logger.info("DATA QUALITY VALIDATION")
        logger.info("=" * 60)

        is_valid, errors = DataValidator.validate_dataframe(df)
        logger.info(f"\nDataFrame valid: {is_valid}")
        if errors:
            logger.warning("Errors:")
            for err in errors:
                logger.warning(f"  - {err}")

        report = DataValidator.get_data_quality_report(df)
        logger.info(f"\nData Quality Report:")
        logger.info(f"  Rows: {report['rows']}")
        logger.info(f"  Devices: {report['devices']}")
        logger.info(f"  Time range: {report['time_range']['start']} to {report['time_range']['end']}")
        logger.info(f"\nSignal strength stats:")
        if 'avg_signal' in report['field_stats']:
            stats = report['field_stats']['avg_signal']
            logger.info(f"  Mean: {stats['mean']:.1f} dBm")
            logger.info(f"  Range: [{stats['min']:.1f}, {stats['max']:.1f}]")
            logger.info(f"  Out of range: {stats['out_of_range_pct']:.1f}%")

        logger.info(f"\nNetwork types:")
        if 'network_types' in report['field_stats']:
            for net_type, count in report['field_stats']['network_types'].items():
                logger.info(f"  {net_type}: {count}")

        await ch.disconnect()

    asyncio.run(test_validation())
