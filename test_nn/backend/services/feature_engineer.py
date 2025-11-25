import pandas as pd
import numpy as np
from typing import Any
from backend.services.clickhouse_client import ClickHouseClient

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
        """Получение hourly агрегатов из materialized view

        Аргументы:
            device_id: ID устройства (None = все)
            hours: количество часов назад

        Возвращает:
            DataFrame с признаками"""

        device_filter = f"AND device_id = '{device_id}'" if device_id else ""

        query = f"""
        SELECT
            device_id,
            hour,
            region,
            event_count,
            avg_activity,
            std_activity,
            min_activity,
            max_activity,
            avg_lat,
            avg_lon,
            std_lat,
            std_lon,
            p95_activity,
            p05_activity
        FROM hourly_features
        WHERE hour >= now() - INTERVAL {hours} HOUR
        {device_filter}
        ORDER BY hour DESC
        """

        result = await self.ch.query(query)
        df = pd.DataFrame(result)

        if df.empty:
            return df

        df['activity_range'] = df['max_activity'] - df['min_activity']
        df['is_moving'] = (df['std_lat'] > 0.001) | (df['std_lon'] > 0.001)
        df['hour_of_day'] = pd.to_datetime(df['hour']).dt.hour

        return df

    async def get_regional_density(self, hours: int = 24) -> pd.DataFrame:
        """Получение плотности по регионам"""

        query = f"""
        SELECT
            region,
            hour,
            total_events,
            unique_devices,
            avg_regional_activity,
            std_regional_activity
        FROM regional_density
        WHERE hour >= now() - INTERVAL {hours} HOUR
        ORDER BY hour DESC
        """

        result = await self.ch.query(query)
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
        Продвинутые статистические признаки
        """
        df = df.copy()

        df['activity_skewness'] = df['avg_activity'].rolling(window=12, min_periods=3).skew().fillna(0)
        df['activity_kurtosis'] = df['avg_activity'].rolling(window=12, min_periods=3).kurt().fillna(0)

        df['activity_q25'] = df['avg_activity'].rolling(window=24, min_periods=6).quantile(0.25).fillna(0)
        df['activity_q75'] = df['avg_activity'].rolling(window=24, min_periods=6).quantile(0.75).fillna(0)
        df['activity_iqr'] = df['activity_q75'] - df['activity_q25']

        mean_act = df['avg_activity'].rolling(window=24, min_periods=1).mean()
        std_act = df['avg_activity'].rolling(window=24, min_periods=1).std()
        df['activity_cv'] = (std_act / (mean_act + 1e-8)).fillna(0)

        df['activity_zscore'] = ((df['avg_activity'] - mean_act) / (std_act + 1e-8)).fillna(0)

        df['activity_range_ratio'] = df['activity_range'] / (df['avg_activity'] + 1e-8)

        return df

    def compute_rolling_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Rolling aggregates для различных окон
        """
        df = df.copy()

        df['activity_ema_3'] = df['avg_activity'].ewm(span=3, adjust=False).mean()
        df['activity_ema_12'] = df['avg_activity'].ewm(span=12, adjust=False).mean()
        df['activity_ema_24'] = df['avg_activity'].ewm(span=24, adjust=False).mean()

        rolling_max = df['avg_activity'].rolling(window=12, min_periods=1).max()
        rolling_min = df['avg_activity'].rolling(window=12, min_periods=1).min()
        df['activity_maxmin_ratio'] = rolling_max / (rolling_min + 1e-8)

        df['activity_trend'] = df['activity_ema_3'] - df['activity_ema_12']

        df['activity_std_3h'] = df['avg_activity'].rolling(window=3, min_periods=1).std().fillna(0)
        df['activity_std_6h'] = df['avg_activity'].rolling(window=6, min_periods=1).std().fillna(0)
        df['activity_std_12h'] = df['avg_activity'].rolling(window=12, min_periods=1).std().fillna(0)

        activity_changes = df['avg_activity'].diff()
        df['activity_volatility'] = activity_changes.rolling(window=6, min_periods=1).std().fillna(0)

        return df

    def compute_autocorrelation_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Autocorrelation признаки для выявления периодических паттернов
        """
        df = df.copy()

        for lag in [1, 3, 6, 24]:
            lagged = df['avg_activity'].shift(lag)
            window = 24
            correlation = []
            for i in range(len(df)):
                start = max(0, i - window + 1)
                if i >= lag:
                    x = df['avg_activity'].iloc[start:i+1].values
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
            df[f'activity_acf_lag{lag}'] = correlation

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
        Поведенческие паттерны
        """
        df = df.copy()

        df['event_rate'] = df['event_count'].diff().fillna(0)
        df['event_rate_change'] = df['event_rate'].diff().fillna(0)

        df['activity_stability'] = 1 / (df['std_activity'] + 1e-8)

        mean_events = df['event_count'].rolling(window=12, min_periods=1).mean()
        var_events = df['event_count'].rolling(window=12, min_periods=1).var()
        df['event_burstiness'] = (var_events / (mean_events + 1e-8)).fillna(0)

        time_since_peak = []
        for i in range(len(df)):
            start = max(0, i - 24 + 1)
            window = df['avg_activity'].iloc[start:i+1]
            if len(window) > 0:
                peak_idx = window.argmax()
                time_since = i - (start + peak_idx)
                time_since_peak.append(time_since)
            else:
                time_since_peak.append(0)
        df['time_since_peak_activity'] = time_since_peak

        activity_conc = []
        for i in range(len(df)):
            start = max(0, i - 24 + 1)
            window_activity = df['avg_activity'].iloc[start:i+1].values
            if len(window_activity) > 1:
                sorted_act = np.sort(window_activity)
                n = len(sorted_act)
                index = np.arange(1, n + 1)
                gini = (2 * np.sum(index * sorted_act)) / (n * np.sum(sorted_act)) - (n + 1) / n
                activity_conc.append(gini if not np.isnan(gini) else 0)
            else:
                activity_conc.append(0)
        df['activity_concentration'] = activity_conc

        return df

    def prepare_timeseries(
        self,
        df: pd.DataFrame,
        window_size: int = 24,
        use_extended_features: bool = True,
    ) -> np.ndarray:
        """Подготовка временных рядов для ML модели

        Аргументы:
            df: DataFrame с признаками
            window_size: размер окна
            use_extended_features: использовать ли расширенный набор признаков

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

        base_feature_cols = [
            'event_count',
            'avg_activity',
            'std_activity',
            'activity_range',
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
        ]

        extended_feature_cols = base_feature_cols + [
            'activity_skewness',
            'activity_kurtosis',
            'activity_q25',
            'activity_q75',
            'activity_iqr',
            'activity_cv',
            'activity_zscore',
            'activity_range_ratio',
            'activity_ema_3',
            'activity_ema_12',
            'activity_ema_24',
            'activity_maxmin_ratio',
            'activity_trend',
            'activity_std_3h',
            'activity_std_6h',
            'activity_std_12h',
            'activity_volatility',
            'activity_acf_lag1',
            'activity_acf_lag3',
            'activity_acf_lag6',
            'activity_acf_lag24',
            'distance_from_home',
            'unique_locations_24h',
            'location_revisit_rate',
            'radius_of_gyration',
            'event_rate',
            'event_rate_change',
            'activity_stability',
            'event_burstiness',
            'time_since_peak_activity',
            'activity_concentration',
        ]

        feature_cols = extended_feature_cols if use_extended_features else base_feature_cols

        available_cols = [col for col in feature_cols if col in df.columns]

        if len(available_cols) < len(feature_cols):
            missing = set(feature_cols) - set(available_cols)
            print(f"Warning: Missing {len(missing)} columns: {missing}")

        features = df[available_cols].values.astype(float)

        features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

        if self.global_mean is not None and self.global_std is not None:
            if len(self.global_mean) != features.shape[1]:
                print(f"Warning: Normalization stats mismatch. Expected {features.shape[1]}, got {len(self.global_mean)}")
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

    def get_feature_names(self, extended: bool = True) -> list[str]:
        """Возвращает список имён признаков

        Аргументы:
            extended: если True, возвращает полный набор (67), иначе базовый (17)"""
        base_features = [
            'event_count',
            'avg_activity',
            'std_activity',
            'activity_range',
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
        ]

        if not extended:
            return base_features

        extended_features = base_features + [
            'activity_skewness',
            'activity_kurtosis',
            'activity_q25',
            'activity_q75',
            'activity_iqr',
            'activity_cv',
            'activity_zscore',
            'activity_range_ratio',
            'activity_ema_3',
            'activity_ema_12',
            'activity_ema_24',
            'activity_maxmin_ratio',
            'activity_trend',
            'activity_std_3h',
            'activity_std_6h',
            'activity_std_12h',
            'activity_volatility',
            'activity_acf_lag1',
            'activity_acf_lag3',
            'activity_acf_lag6',
            'activity_acf_lag24',
            'distance_from_home',
            'unique_locations_24h',
            'location_revisit_rate',
            'radius_of_gyration',
            'event_rate',
            'event_rate_change',
            'activity_stability',
            'event_burstiness',
            'time_since_peak_activity',
            'activity_concentration',
        ]

        return extended_features
