import pandas as pd
import numpy as np
from typing import Dict, List
from loguru import logger

class AdvancedFeatureEngineer:
    """Дополнительные признаки на основе production данных"""

    @staticmethod
    def compute_signal_dynamics(df: pd.DataFrame) -> pd.DataFrame:
        """
        Signal strength динамика и паттерны

        Признаки:
        - Signal gradient (скорость изменения)
        - Signal stability (стабильность)
        - Signal jumps (резкие скачки)
        - Signal range per hour
        """
        df = df.copy()

        df['signal_gradient'] = df['avg_signal'].diff().fillna(0)
        df['signal_gradient_abs'] = abs(df['signal_gradient'])

        df['signal_acceleration'] = df['signal_gradient'].diff().fillna(0)

        df['signal_stability_score'] = 1 / (df['std_signal'] + 1e-8)

        df['signal_rolling_mean_3h'] = df['avg_signal'].rolling(3, min_periods=1).mean()
        df['signal_rolling_std_6h'] = df['avg_signal'].rolling(6, min_periods=1).std().fillna(0)

        df['signal_jump_indicator'] = (df['signal_gradient_abs'] > 20).astype(int)
        df['signal_jump_count_24h'] = df['signal_jump_indicator'].rolling(24, min_periods=1).sum()

        df['estimated_distance'] = 10 ** ((0 - df['avg_signal']) / 20)
        df['estimated_distance'] = df['estimated_distance'].clip(0, 100)  

        return df

    @staticmethod
    def compute_network_patterns(df: pd.DataFrame) -> pd.DataFrame:
        """
        Network type паттерны и переключения

        Признаки:
        - Network switching frequency
        - Network diversity
        - Network persistence (сколько часов подряд один тип)
        """
        df = df.copy()

        if 'network_type' in df.columns:
            df['network_changed'] = (df['network_type'] != df['network_type'].shift(1)).astype(int)
            df['network_switch_count_12h'] = df['network_changed'].rolling(12, min_periods=1).sum()

            persistence = []
            current_persist = 1
            for i in range(len(df)):
                if i > 0 and df.iloc[i]['network_type'] == df.iloc[i-1]['network_type']:
                    current_persist += 1
                else:
                    current_persist = 1
                persistence.append(current_persist)
            df['network_persistence'] = persistence

            def network_diversity(window):
                if len(window) == 0:
                    return 0
                unique = window.nunique()
                return unique / len(window)

            df['network_diversity_24h'] = df['network_type'].rolling(24, min_periods=1).apply(
                lambda x: x.nunique() / len(x) if len(x) > 0 else 0, raw=False
            )

        if 'is_wifi' in df.columns:
            df['wifi_usage_24h'] = df['is_wifi'].rolling(24, min_periods=1).sum()
            df['bluetooth_usage_24h'] = df['is_bluetooth'].rolling(24, min_periods=1).sum()
            df['gsm_usage_24h'] = df['is_gsm'].rolling(24, min_periods=1).sum()

            df['dominant_network_score'] = df[['wifi_usage_24h', 'bluetooth_usage_24h', 'gsm_usage_24h']].max(axis=1) / 24

        return df

    @staticmethod
    def compute_vendor_patterns(df: pd.DataFrame) -> pd.DataFrame:
        """
        Vendor (производитель) паттерны

        Признаки:
        - Vendor consistency (смена устройства)
        - Vendor-location affinity
        """
        df = df.copy()

        if 'vendor' in df.columns:
            df['vendor_changed'] = (df['vendor'] != df['vendor'].shift(1)).astype(int)
            df['vendor_change_count_7d'] = df['vendor_changed'].rolling(24*7, min_periods=1).sum()

            persistence = []
            current_persist = 1
            for i in range(len(df)):
                if i > 0 and df.iloc[i]['vendor'] == df.iloc[i-1]['vendor']:
                    current_persist += 1
                else:
                    current_persist = 1
                persistence.append(current_persist)
            df['vendor_persistence'] = persistence

        return df

    @staticmethod
    def compute_cross_feature_interactions(df: pd.DataFrame) -> pd.DataFrame:
        """
        Взаимодействия между признаками

        Комбинации:
        - Signal × Velocity (сильный сигнал + высокая скорость)
        - Signal × Network type
        - Network × Location patterns
        """
        df = df.copy()

        if 'avg_signal' in df.columns and 'velocity' in df.columns:
            df['signal_velocity_product'] = abs(df['avg_signal']) * df['velocity']
            df['strong_signal_high_speed'] = ((abs(df['avg_signal']) > 60) & (df['velocity'] > 3)).astype(int)

            df['weak_signal_stationary'] = ((abs(df['avg_signal']) < 40) & (df['velocity'] < 0.1)).astype(int)

        if 'avg_signal' in df.columns:
            if 'is_wifi' in df.columns:
                df['wifi_signal_strength'] = df['is_wifi'] * abs(df['avg_signal'])
            if 'is_bluetooth' in df.columns:
                df['bluetooth_signal_strength'] = df['is_bluetooth'] * abs(df['avg_signal'])
                df['bluetooth_very_close'] = (df['is_bluetooth'] & (abs(df['avg_signal']) > 70)).astype(int)

        if 'is_gsm' in df.columns and 'velocity' in df.columns:
            df['gsm_high_velocity'] = (df['is_gsm'] & (df['velocity'] > 5)).astype(int)

        if 'signal_stability_score' in df.columns and 'stationarity_score' in df.columns:
            df['stable_signal_stationary'] = df['signal_stability_score'] * df['stationarity_score']

        return df

    @staticmethod
    def compute_all_advanced_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        Применить все дополнительные признаки

        Args:
            df: DataFrame с базовыми признаками

        Returns:
            DataFrame с добавленными advanced признаками
        """
        df = AdvancedFeatureEngineer.compute_signal_dynamics(df)
        df = AdvancedFeatureEngineer.compute_network_patterns(df)
        df = AdvancedFeatureEngineer.compute_vendor_patterns(df)
        df = AdvancedFeatureEngineer.compute_cross_feature_interactions(df)

        return df

    @staticmethod
    def get_advanced_feature_names() -> List[str]:
        """Список всех дополнительных признаков"""
        return [
            'signal_gradient',
            'signal_gradient_abs',
            'signal_acceleration',
            'signal_stability_score',
            'signal_rolling_mean_3h',
            'signal_rolling_std_6h',
            'signal_jump_indicator',
            'signal_jump_count_24h',
            'estimated_distance',

            'network_changed',
            'network_switch_count_12h',
            'network_persistence',
            'network_diversity_24h',
            'wifi_usage_24h',
            'bluetooth_usage_24h',
            'gsm_usage_24h',
            'dominant_network_score',

            'vendor_changed',
            'vendor_change_count_7d',
            'vendor_persistence',

            'signal_velocity_product',
            'strong_signal_high_speed',
            'weak_signal_stationary',
            'wifi_signal_strength',
            'bluetooth_signal_strength',
            'bluetooth_very_close',
            'gsm_high_velocity',
            'stable_signal_stationary',
        ]


def get_total_feature_count(use_base: bool = True, use_extended: bool = True, use_advanced: bool = True) -> int:
    """
    Подсчет общего количества признаков

    Args:
        use_base: Использовать базовые (20)
        use_extended: Использовать расширенные (+50 = 70)
        use_advanced: Использовать advanced (+28 = 98)

    Returns:
        Общее количество признаков
    """
    count = 0
    if use_base:
        count += 20 
    if use_extended:
        count += 50 
    if use_advanced:
        count += 28 
    return count


if __name__ == "__main__":
    logger.info("Advanced Feature Engineering для production данных")
    logger.info(f"Новых признаков: {len(AdvancedFeatureEngineer.get_advanced_feature_names())}")
    logger.info(f"\nТипы признаков:")
    logger.info(f"  - Signal dynamics: 9")
    logger.info(f"  - Network patterns: 8")
    logger.info(f"  - Vendor patterns: 3")
    logger.info(f"  - Cross-feature interactions: 8")
    logger.info(f"\nИтого: базовые (20) + расширенные (50) + advanced (28) = 98 признаков")
