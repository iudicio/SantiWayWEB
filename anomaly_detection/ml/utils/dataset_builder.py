from __future__ import annotations

import numpy as np
import pandas as pd

def build_windows(
    df: pd.DataFrame,
    feature_cols: list[str],
    window_size: int,
) -> np.ndarray:
    """Build sliding windows from feature dataframe.

    Returns ndarray of размерность (n_samples, window_size, n_features)"""
    if df.empty or len(df) < window_size:
        return np.array([])

    df = df.sort_values('hour' if 'hour' in df.columns else df.columns[0])
    features = df[feature_cols].values.astype(float)
    mean = features.mean(axis=0)
    std = features.std(axis=0) + 1e-8
    norm = (features - mean) / std

    windows: list[np.ndarray] = []
    for i in range(len(norm) - window_size + 1):
        windows.append(norm[i:i + window_size])

    return np.array(windows) if windows else np.array([])
