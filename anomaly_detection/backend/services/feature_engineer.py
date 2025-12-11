import pandas as pd
import numpy as np
from typing import Any
from loguru import logger
from backend.services.clickhouse_client import ClickHouseClient
from backend.services.advanced_features import AdvancedFeatureEngineer

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Расчёт расстояния между двумя точками в километрах
    """
    R = 6371

    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))

    return R * c

def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Расчёт направления движения (азимут) в градусах
    """
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])

    dlon = lon2 - lon1

    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)

    bearing = np.arctan2(x, y)
    bearing = np.degrees(bearing)
    bearing = (bearing + 360) % 360

    return bearing

class FeatureEngineer:
    """Вычисление признаков для аномалий"""

    def __init__(self, ch_client: ClickHouseClient, global_mean: np.ndarray = None, global_std: np.ndarray = None):
        self.ch = ch_client
        self.global_mean = global_mean
        self.global_std = global_std

    async def get_hourly_features(
        self,
        device_id: str | None = None,
        hours: int = 24,
    ) -> pd.DataFrame:
        """Получение hourly агрегатов из materialized view (production data)

        Защита от SQL Injection через parameterized queries

        Аргументы:
            device_id: ID устройства (None = все)
            hours: количество часов назад

        Возвращает:
            DataFrame с признаками из way_data"""

        if device_id:
            device_filter = "AND device_id = %s"
            params = [hours, device_id]
        else:
            device_filter = ""
            params = [hours]

        query = f"""
        SELECT
            device_id,
            hour,
            folder_name,
            vendor,
            network_type,
            event_count,
            avg_signal,
            std_signal,
            min_signal,
            max_signal,
            avg_lat,
            avg_lon,
            std_lat,
            std_lon,
            p95_signal,
            p05_signal,
            alert_count,
            ignored_count
        FROM anomaly_ml.hourly_features
        WHERE hour >= now() - INTERVAL %s HOUR
        {device_filter}
        ORDER BY hour DESC
        """

        result = await self.ch.query(query, params)
        df = pd.DataFrame(result)

        if df.empty:
            return df

        df['signal_range'] = df['max_signal'] - df['min_signal']
        df['is_moving'] = (df['std_lat'] > 0.001) | (df['std_lon'] > 0.001)
        df['hour_of_day'] = pd.to_datetime(df['hour']).dt.hour

        df['is_wifi'] = (df['network_type'] == 'wifi').astype(int)
        df['is_bluetooth'] = (df['network_type'] == 'bluetooth').astype(int)
        df['is_gsm'] = (df['network_type'] == 'gsm').astype(int)

        return df

    async def get_folder_density(self, hours: int = 24) -> pd.DataFrame:
        """Получение плотности по папкам (folders)

        Защита от SQL Injection через parameterized queries
        """

        query = """
        SELECT
            folder_name,
            system_folder_name,
            hour,
            total_events,
            unique_devices,
            unique_vendors,
            avg_folder_signal,
            std_folder_signal,
            wifi_count,
            bluetooth_count,
            gsm_count
        FROM anomaly_ml.folder_density
        WHERE hour >= now() - INTERVAL %s HOUR
        ORDER BY hour DESC
        """

        result = await self.ch.query(query, [hours])
        return pd.DataFrame(result)

    def compute_velocity_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Вычисление признаков скорости и направления движения

        Аргументы:
            df: DataFrame с колонками hour, avg_lat, avg_lon

        Возвращает:
            DataFrame с добавленными признаками velocity"""

        df = df.sort_values('hour').copy()

        velocities = [0.0]
        for i in range(1, len(df)):
            dist = haversine_distance(
                df.iloc[i - 1]['avg_lat'], df.iloc[i - 1]['avg_lon'],
                df.iloc[i]['avg_lat'], df.iloc[i]['avg_lon']
            )
            velocities.append(dist)

        df['velocity'] = velocities

        bearings = [0.0]
        for i in range(1, len(df)):
            bearing = calculate_bearing(
                df.iloc[i - 1]['avg_lat'], df.iloc[i - 1]['avg_lon'],
                df.iloc[i]['avg_lat'], df.iloc[i]['avg_lon']
            )
            bearings.append(bearing)

        df['bearing'] = bearings

        direction_changes = [0.0]
        for i in range(1, len(df)):
            change = abs(bearings[i] - bearings[i - 1])
            if change > 180:
                change = 360 - change
            direction_changes.append(change)

        df['direction_change'] = direction_changes

        accelerations = [0.0]
        for i in range(1, len(df)):
            accelerations.append(velocities[i] - velocities[i - 1])

        df['acceleration'] = accelerations

        df['velocity_std'] = df['velocity'].rolling(window=3, min_periods=1).std().fillna(0)
        df['velocity_max'] = df['velocity'].rolling(window=3, min_periods=1).max().fillna(0)

        return df

    def compute_location_entropy(self, df: pd.DataFrame, n_bins: int = 10) -> pd.DataFrame:
        """
        Вычисление энтропии локаций (разнообразие посещаемых мест)

        Низкая энтропия = устройство в одном месте (подозрительно при слежке)
        """

        df = df.copy()

        lat_bins = pd.cut(df['avg_lat'], bins=n_bins, labels=False)
        lon_bins = pd.cut(df['avg_lon'], bins=n_bins, labels=False)

        df['location_cell'] = lat_bins.astype(str) + '_' + lon_bins.astype(str)

        window_size = 6
        entropies = []

        for i in range(len(df)):
            start_idx = max(0, i - window_size + 1)
            window = df.iloc[start_idx:i + 1]['location_cell']

            value_counts = window.value_counts(normalize=True)
            entropy = -np.sum(value_counts * np.log2(value_counts + 1e-10))
            entropies.append(entropy)

        df['location_entropy'] = entropies

        return df

    def compute_temporal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Временные признаки
        """

        df = df.copy()

        df['hour_of_day'] = pd.to_datetime(df['hour']).dt.hour

        df['day_of_week'] = pd.to_datetime(df['hour']).dt.dayofweek

        df['is_night'] = df['hour_of_day'].apply(lambda x: 1 if 0 <= x <= 6 else 0)

        df['is_weekend'] = df['day_of_week'].apply(lambda x: 1 if x >= 5 else 0)

        df['hour_sin'] = np.sin(2 * np.pi * df['hour_of_day'] / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour_of_day'] / 24)

        return df

    def compute_stationarity_score(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Оценка стационарности (долго ли устройство на одном месте)
        """

        df = df.copy()

        window_size = 4

        stationarity_scores = []
        for i in range(len(df)):
            start_idx = max(0, i - window_size + 1)
            window = df.iloc[start_idx:i + 1]

            if len(window) < 2:
                stationarity_scores.append(0)
                continue

            total_distance = 0
            for j in range(1, len(window)):
                dist = haversine_distance(
                    window.iloc[j - 1]['avg_lat'], window.iloc[j - 1]['avg_lon'],
                    window.iloc[j]['avg_lat'], window.iloc[j]['avg_lon']
                )
                total_distance += dist

            score = max(0, 1 - total_distance / 0.5)
            stationarity_scores.append(score)

        df['stationarity_score'] = stationarity_scores

        return df

    def compute_statistical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Продвинутые статистические признаки на основе signal strength
        """
        df = df.copy()

        df['signal_skewness'] = df['avg_signal'].rolling(window=12, min_periods=3).skew().fillna(0)
        df['signal_kurtosis'] = df['avg_signal'].rolling(window=12, min_periods=3).kurt().fillna(0)

        df['signal_q25'] = df['avg_signal'].rolling(window=24, min_periods=6).quantile(0.25).fillna(0)
        df['signal_q75'] = df['avg_signal'].rolling(window=24, min_periods=6).quantile(0.75).fillna(0)
        df['signal_iqr'] = df['signal_q75'] - df['signal_q25']

        mean_sig = df['avg_signal'].rolling(window=24, min_periods=1).mean()
        std_sig = df['avg_signal'].rolling(window=24, min_periods=1).std()
        df['signal_cv'] = (std_sig / (mean_sig + 1e-8)).fillna(0)

        df['signal_zscore'] = ((df['avg_signal'] - mean_sig) / (std_sig + 1e-8)).fillna(0)

        df['signal_range_ratio'] = df['signal_range'] / (abs(df['avg_signal']) + 1e-8)

        return df

    def compute_rolling_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Rolling aggregates для различных окон (на основе signal strength)
        """
        df = df.copy()

        df['signal_ema_3'] = df['avg_signal'].ewm(span=3, adjust=False).mean()
        df['signal_ema_12'] = df['avg_signal'].ewm(span=12, adjust=False).mean()
        df['signal_ema_24'] = df['avg_signal'].ewm(span=24, adjust=False).mean()

        rolling_max = df['avg_signal'].rolling(window=12, min_periods=1).max()
        rolling_min = df['avg_signal'].rolling(window=12, min_periods=1).min()
        df['signal_maxmin_ratio'] = rolling_max / (abs(rolling_min) + 1e-8)

        df['signal_trend'] = df['signal_ema_3'] - df['signal_ema_12']

        df['signal_std_3h'] = df['avg_signal'].rolling(window=3, min_periods=1).std().fillna(0)
        df['signal_std_6h'] = df['avg_signal'].rolling(window=6, min_periods=1).std().fillna(0)
        df['signal_std_12h'] = df['avg_signal'].rolling(window=12, min_periods=1).std().fillna(0)

        signal_changes = df['avg_signal'].diff()
        df['signal_volatility'] = signal_changes.rolling(window=6, min_periods=1).std().fillna(0)

        return df

    def compute_autocorrelation_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Autocorrelation признаки для выявления периодических паттернов (signal strength)
        """
        df = df.copy()

        for lag in [1, 3, 6, 24]:
            lagged = df['avg_signal'].shift(lag)
            window = 24
            correlation = []
            for i in range(len(df)):
                start = max(0, i - window + 1)
                if i >= lag:
                    x = df['avg_signal'].iloc[start:i+1].values
                    y = lagged.iloc[start:i+1].values
                    if len(x) > 1 and not np.isnan(y).all():
                        mask = ~np.isnan(y)
                        if mask.sum() > 1:
                            corr = np.corrcoef(x[mask], y[mask])[0, 1]
                            correlation.append(corr if not np.isnan(corr) else 0)
                        else:
                            correlation.append(0)
                    else:
                        correlation.append(0)
                else:
                    correlation.append(0)
            df[f'signal_acf_lag{lag}'] = correlation

        return df

    def compute_spatial_advanced_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Продвинутые пространственные признаки
        """
        df = df.copy()

        centroid_lat = df['avg_lat'].mean()
        centroid_lon = df['avg_lon'].mean()

        distances_from_home = []
        for idx, row in df.iterrows():
            dist = haversine_distance(row['avg_lat'], row['avg_lon'], centroid_lat, centroid_lon)
            distances_from_home.append(dist)

        df['distance_from_home'] = distances_from_home

        lat_bins = pd.cut(df['avg_lat'], bins=20, labels=False)
        lon_bins = pd.cut(df['avg_lon'], bins=20, labels=False)
        df['location_cell_id'] = lat_bins.astype(str) + '_' + lon_bins.astype(str)

        unique_locs = []
        for i in range(len(df)):
            start = max(0, i - 24 + 1)
            window_cells = df['location_cell_id'].iloc[start:i+1]
            unique_locs.append(window_cells.nunique())
        df['unique_locations_24h'] = unique_locs

        revisit_rates = []
        for i in range(len(df)):
            start = max(0, i - 48 + 1)
            window_cells = df['location_cell_id'].iloc[start:i+1]
            if len(window_cells) > 0:
                revisit_rate = 1 - (window_cells.nunique() / len(window_cells))
                revisit_rates.append(revisit_rate)
            else:
                revisit_rates.append(0)
        df['location_revisit_rate'] = revisit_rates

        radius_gyration = []
        for i in range(len(df)):
            start = max(0, i - 24 + 1)
            window = df.iloc[start:i+1]
            if len(window) > 1:
                cent_lat = window['avg_lat'].mean()
                cent_lon = window['avg_lon'].mean()
                distances = [haversine_distance(row['avg_lat'], row['avg_lon'], cent_lat, cent_lon)
                            for _, row in window.iterrows()]
                rog = np.sqrt(np.mean(np.array(distances) ** 2))
                radius_gyration.append(rog)
            else:
                radius_gyration.append(0)
        df['radius_of_gyration'] = radius_gyration

        return df

    def compute_behavioral_patterns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Поведенческие паттерны (на основе signal strength и событий)
        """
        df = df.copy()

        df['event_rate'] = df['event_count'].diff().fillna(0)
        df['event_rate_change'] = df['event_rate'].diff().fillna(0)

        df['signal_stability'] = 1 / (df['std_signal'] + 1e-8)

        mean_events = df['event_count'].rolling(window=12, min_periods=1).mean()
        var_events = df['event_count'].rolling(window=12, min_periods=1).var()
        df['event_burstiness'] = (var_events / (mean_events + 1e-8)).fillna(0)

        time_since_peak = []
        for i in range(len(df)):
            start = max(0, i - 24 + 1)
            window = abs(df['avg_signal'].iloc[start:i+1])
            if len(window) > 0:
                peak_idx = window.argmax()
                time_since = i - (start + peak_idx)
                time_since_peak.append(time_since)
            else:
                time_since_peak.append(0)
        df['time_since_peak_signal'] = time_since_peak

        signal_conc = []
        for i in range(len(df)):
            start = max(0, i - 24 + 1)
            window_signal = abs(df['avg_signal'].iloc[start:i+1].values)
            if len(window_signal) > 1:
                sorted_sig = np.sort(window_signal)
                n = len(sorted_sig)
                index = np.arange(1, n + 1)
                gini = (2 * np.sum(index * sorted_sig)) / (n * np.sum(sorted_sig)) - (n + 1) / n
                signal_conc.append(gini if not np.isnan(gini) else 0)
            else:
                signal_conc.append(0)
        df['signal_concentration'] = signal_conc

        return df

    def prepare_timeseries(
        self,
        df: pd.DataFrame,
        window_size: int = 24,
        use_extended_features: bool = True,
        use_advanced_features: bool = True,
    ) -> np.ndarray:
        """Подготовка временных рядов для ML модели

        Аргументы:
            df: DataFrame с признаками
            window_size: размер окна
            use_extended_features: использовать ли расширенный набор признаков (70)
            use_advanced_features: использовать ли advanced признаки на основе production данных (98)

        Возвращает:
            Numpy array размерность (n_samples, window_size, n_features)"""

        df = df.sort_values('hour').copy()

        df = self.compute_velocity_features(df)
        df = self.compute_location_entropy(df)
        df = self.compute_temporal_features(df)
        df = self.compute_stationarity_score(df)

        if use_extended_features:
            df = self.compute_statistical_features(df)
            df = self.compute_rolling_features(df)
            df = self.compute_autocorrelation_features(df)
            df = self.compute_spatial_advanced_features(df)
            df = self.compute_behavioral_patterns(df)

        if use_advanced_features:
            df = AdvancedFeatureEngineer.compute_all_advanced_features(df)

        base_feature_cols = [
            'event_count',
            'avg_signal',
            'std_signal',
            'signal_range',
            'avg_lat',
            'avg_lon',
            'std_lat',
            'std_lon',
            'velocity',
            'acceleration',
            'direction_change',
            'velocity_std',
            'location_entropy',
            'stationarity_score',
            'hour_sin',
            'hour_cos',
            'is_night',
            'is_wifi',
            'is_bluetooth',
            'is_gsm',
        ]

        extended_feature_cols = base_feature_cols + [
            'signal_skewness',
            'signal_kurtosis',
            'signal_q25',
            'signal_q75',
            'signal_iqr',
            'signal_cv',
            'signal_zscore',
            'signal_range_ratio',
            'signal_ema_3',
            'signal_ema_12',
            'signal_ema_24',
            'signal_maxmin_ratio',
            'signal_trend',
            'signal_std_3h',
            'signal_std_6h',
            'signal_std_12h',
            'signal_volatility',
            'signal_acf_lag1',
            'signal_acf_lag3',
            'signal_acf_lag6',
            'signal_acf_lag24',
            'distance_from_home',
            'unique_locations_24h',
            'location_revisit_rate',
            'radius_of_gyration',
            'event_rate',
            'event_rate_change',
            'signal_stability',
            'event_burstiness',
            'time_since_peak_signal',
            'signal_concentration',
        ]

        advanced_feature_cols = extended_feature_cols + AdvancedFeatureEngineer.get_advanced_feature_names()

        if use_advanced_features:
            feature_cols = advanced_feature_cols
        elif use_extended_features:
            feature_cols = extended_feature_cols
        else:
            feature_cols = base_feature_cols

        available_cols = [col for col in feature_cols if col in df.columns]

        if len(available_cols) < len(feature_cols):
            missing = set(feature_cols) - set(available_cols)
            logger.warning(f"Missing {len(missing)} columns: {missing}")

        features = df[available_cols].values.astype(float)

        features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

        if self.global_mean is not None and self.global_std is not None:
            if len(self.global_mean) != features.shape[1]:
                logger.warning(
                    f"Normalization stats mismatch. Expected {features.shape[1]}, "
                    f"got {len(self.global_mean)}"
                )
                mean = features.mean(axis=0)
                std = features.std(axis=0) + 1e-8
                features_normalized = (features - mean) / std
            else:
                features_normalized = (features - self.global_mean) / self.global_std
        else:
            mean = features.mean(axis=0)
            std = features.std(axis=0) + 1e-8
            features_normalized = (features - mean) / std

        windows: list[np.ndarray] = []
        for i in range(len(features_normalized) - window_size + 1):
            window = features_normalized[i:i + window_size]
            windows.append(window)

        if not windows:
            return np.array([])

        return np.array(windows)

    def get_feature_names(self, extended: bool = True, advanced: bool = True) -> list[str]:
        """Возвращает список имён признаков на основе production данных

        Аргументы:
            extended: если True, возвращает расширенный набор (70 features), иначе базовый (20)
            advanced: если True, возвращает с advanced признаками (98 features total)"""
        base_features = [
            'event_count',
            'avg_signal',
            'std_signal',
            'signal_range',
            'avg_lat',
            'avg_lon',
            'std_lat',
            'std_lon',
            'velocity',
            'acceleration',
            'direction_change',
            'velocity_std',
            'location_entropy',
            'stationarity_score',
            'hour_sin',
            'hour_cos',
            'is_night',
            'is_wifi',
            'is_bluetooth',
            'is_gsm',
        ]

        if not extended and not advanced:
            return base_features

        extended_features = base_features + [
            'signal_skewness',
            'signal_kurtosis',
            'signal_q25',
            'signal_q75',
            'signal_iqr',
            'signal_cv',
            'signal_zscore',
            'signal_range_ratio',
            'signal_ema_3',
            'signal_ema_12',
            'signal_ema_24',
            'signal_maxmin_ratio',
            'signal_trend',
            'signal_std_3h',
            'signal_std_6h',
            'signal_std_12h',
            'signal_volatility',
            'signal_acf_lag1',
            'signal_acf_lag3',
            'signal_acf_lag6',
            'signal_acf_lag24',
            'distance_from_home',
            'unique_locations_24h',
            'location_revisit_rate',
            'radius_of_gyration',
            'event_rate',
            'event_rate_change',
            'signal_stability',
            'event_burstiness',
            'time_since_peak_signal',
            'signal_concentration',
        ]

        if not advanced:
            return extended_features

        advanced_features = extended_features + AdvancedFeatureEngineer.get_advanced_feature_names()
        return advanced_features
