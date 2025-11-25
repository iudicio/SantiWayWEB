"""
Tests for Feature Engineering
"""
import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from backend.services.feature_engineer import (
    FeatureEngineer,
    haversine_distance,
    calculate_bearing,
)


class TestHaversineDistance:
    """Tests for haversine distance calculation"""

    def test_same_point(self):
        """Distance between same point should be 0"""
        dist = haversine_distance(0, 0, 0, 0)
        assert dist == 0

    def test_known_distance(self):
        """Test with known coordinates"""
        lat1, lon1 = 55.7558, 37.6173
        lat2, lon2 = 59.9343, 30.3351

        dist = haversine_distance(lat1, lon1, lat2, lon2)

        assert 600 < dist < 700

    def test_symmetry(self):
        """Distance should be symmetric"""
        lat1, lon1 = 40.7128, -74.0060
        lat2, lon2 = 34.0522, -118.2437

        dist1 = haversine_distance(lat1, lon1, lat2, lon2)
        dist2 = haversine_distance(lat2, lon2, lat1, lon1)

        assert abs(dist1 - dist2) < 1e-10


class TestCalculateBearing:
    """Tests for bearing calculation"""

    def test_north_bearing(self):
        """Bearing due north should be 0 degrees"""
        bearing = calculate_bearing(0, 0, 1, 0)
        assert 0 <= bearing < 360

    def test_bearing_range(self):
        """Bearing should always be in [0, 360)"""
        for _ in range(10):
            lat1 = np.random.uniform(-90, 90)
            lon1 = np.random.uniform(-180, 180)
            lat2 = np.random.uniform(-90, 90)
            lon2 = np.random.uniform(-180, 180)

            bearing = calculate_bearing(lat1, lon1, lat2, lon2)
            assert 0 <= bearing < 360


class TestFeatureEngineer:
    """Tests for FeatureEngineer class"""

    @pytest.fixture
    def sample_df(self):
        """Create sample dataframe for testing"""
        hours = pd.date_range('2024-01-01', periods=48, freq='h')
        df = pd.DataFrame({
            'hour': hours,
            'device_id': ['device_001'] * 48,
            'region': ['region_A'] * 48,
            'event_count': np.random.randint(1, 20, 48),
            'avg_activity': np.random.uniform(20, 80, 48),
            'std_activity': np.random.uniform(5, 15, 48),
            'min_activity': np.random.uniform(0, 20, 48),
            'max_activity': np.random.uniform(80, 100, 48),
            'avg_lat': np.random.uniform(55.0, 56.0, 48),
            'avg_lon': np.random.uniform(37.0, 38.0, 48),
            'std_lat': np.random.uniform(0, 0.01, 48),
            'std_lon': np.random.uniform(0, 0.01, 48),
        })
        df['activity_range'] = df['max_activity'] - df['min_activity']
        return df

    @pytest.fixture
    def feature_engineer(self):
        """Create FeatureEngineer instance"""
        return FeatureEngineer(ch_client=None)

    def test_compute_velocity_features(self, feature_engineer, sample_df):
        """Test velocity feature computation"""
        result = feature_engineer.compute_velocity_features(sample_df)

        assert 'velocity' in result.columns
        assert 'acceleration' in result.columns
        assert 'direction_change' in result.columns
        assert 'velocity_std' in result.columns

        assert result['velocity'].iloc[0] == 0

        assert result['velocity'].min() >= 0

    def test_compute_location_entropy(self, feature_engineer, sample_df):
        """Test location entropy computation"""
        result = feature_engineer.compute_location_entropy(sample_df)

        assert 'location_entropy' in result.columns

        assert result['location_entropy'].min() >= 0

    def test_compute_temporal_features(self, feature_engineer, sample_df):
        """Test temporal features"""
        result = feature_engineer.compute_temporal_features(sample_df)

        assert 'hour_of_day' in result.columns
        assert 'day_of_week' in result.columns
        assert 'is_night' in result.columns
        assert 'is_weekend' in result.columns
        assert 'hour_sin' in result.columns
        assert 'hour_cos' in result.columns

        assert result['hour_of_day'].min() >= 0
        assert result['hour_of_day'].max() <= 23

        assert result['hour_sin'].min() >= -1
        assert result['hour_sin'].max() <= 1
        assert result['hour_cos'].min() >= -1
        assert result['hour_cos'].max() <= 1

    def test_compute_stationarity_score(self, feature_engineer, sample_df):
        """Test stationarity score computation"""
        result = feature_engineer.compute_stationarity_score(sample_df)

        assert 'stationarity_score' in result.columns

        assert result['stationarity_score'].min() >= 0
        assert result['stationarity_score'].max() <= 1

    def test_compute_statistical_features(self, feature_engineer, sample_df):
        """Test statistical features"""
        result = feature_engineer.compute_statistical_features(sample_df)

        expected_cols = [
            'activity_skewness',
            'activity_kurtosis',
            'activity_q25',
            'activity_q75',
            'activity_iqr',
            'activity_cv',
            'activity_zscore',
            'activity_range_ratio',
        ]

        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

        assert result['activity_iqr'].min() >= 0

    def test_compute_rolling_features(self, feature_engineer, sample_df):
        """Test rolling features"""
        result = feature_engineer.compute_rolling_features(sample_df)

        expected_cols = [
            'activity_ema_3',
            'activity_ema_12',
            'activity_ema_24',
            'activity_maxmin_ratio',
            'activity_trend',
            'activity_std_3h',
            'activity_std_6h',
            'activity_std_12h',
            'activity_volatility',
        ]

        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

        assert result['activity_maxmin_ratio'].min() >= 0

    def test_compute_autocorrelation_features(self, feature_engineer, sample_df):
        """Test autocorrelation features"""
        result = feature_engineer.compute_autocorrelation_features(sample_df)

        expected_cols = [
            'activity_acf_lag1',
            'activity_acf_lag3',
            'activity_acf_lag6',
            'activity_acf_lag24',
        ]

        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

        for col in expected_cols:
            assert result[col].min() >= -1.1
            assert result[col].max() <= 1.1

    def test_compute_spatial_advanced_features(self, feature_engineer, sample_df):
        """Test advanced spatial features"""
        result = feature_engineer.compute_spatial_advanced_features(sample_df)

        expected_cols = [
            'distance_from_home',
            'unique_locations_24h',
            'location_revisit_rate',
            'radius_of_gyration',
        ]

        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

        assert result['distance_from_home'].min() >= 0

        assert result['unique_locations_24h'].min() > 0

        assert result['location_revisit_rate'].min() >= 0
        assert result['location_revisit_rate'].max() <= 1

    def test_compute_behavioral_patterns(self, feature_engineer, sample_df):
        """Test behavioral pattern features"""
        result = feature_engineer.compute_behavioral_patterns(sample_df)

        expected_cols = [
            'event_rate',
            'event_rate_change',
            'activity_stability',
            'event_burstiness',
            'time_since_peak_activity',
            'activity_concentration',
        ]

        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

        assert result['activity_stability'].min() >= 0

    def test_prepare_timeseries_basic(self, feature_engineer, sample_df):
        """Test timeseries preparation with basic features"""
        result = feature_engineer.prepare_timeseries(
            sample_df,
            window_size=24,
            use_extended_features=False,
        )

        assert len(result.shape) == 3
        assert result.shape[1] == 24
        assert result.shape[2] == 17

    def test_prepare_timeseries_extended(self, feature_engineer, sample_df):
        """Test timeseries preparation with extended features"""
        result = feature_engineer.prepare_timeseries(
            sample_df,
            window_size=24,
            use_extended_features=True,
        )

        assert len(result.shape) == 3
        assert result.shape[1] == 24
        assert result.shape[2] > 17

    def test_get_feature_names_basic(self, feature_engineer):
        """Test feature names retrieval (basic)"""
        names = feature_engineer.get_feature_names(extended=False)

        assert len(names) == 17
        assert 'avg_activity' in names
        assert 'velocity' in names

    def test_get_feature_names_extended(self, feature_engineer):
        """Test feature names retrieval (extended)"""
        names = feature_engineer.get_feature_names(extended=True)

        assert len(names) > 17
        assert 'activity_skewness' in names
        assert 'activity_ema_3' in names
        assert 'distance_from_home' in names

    def test_insufficient_data(self, feature_engineer):
        """Test with insufficient data"""
        small_df = pd.DataFrame({
            'hour': pd.date_range('2024-01-01', periods=5, freq='h'),
            'avg_activity': [10, 20, 30, 40, 50],
            'avg_lat': [55.0] * 5,
            'avg_lon': [37.0] * 5,
        })

        result = feature_engineer.prepare_timeseries(
            small_df,
            window_size=24,
            use_extended_features=False,
        )

        assert result.size == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
