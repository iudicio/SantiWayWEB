import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
import pandas as pd
from pathlib import Path
import sys
from loguru import logger
import asyncio
import json

sys.path.append(str(Path(__file__).parent.parent))
from backend.services.advanced_features import AdvancedFeatureEngineer
from backend.services.model_tcn import TCN_Autoencoder
from backend.services.clickhouse_client import ClickHouseClient
from backend.services.feature_engineer import FeatureEngineer
from backend.utils.config import settings

class TimeSeriesDataset(Dataset):
    """Dataset для временных рядов"""

    def __init__(self, data: np.ndarray):
        """Аргументы:
            data: размерность (n_samples, window_size, n_features)"""
        self.data = torch.FloatTensor(data)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        return self.data[idx].permute(1, 0)

async def prepare_training_data(ch_client: ClickHouseClient, days: int = 30) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Подготовка данных для обучения из ClickHouse production (way_data) с глобальной нормализацией"""

    logger.info("Fetching data from ClickHouse production database (way_data)...")

    fe = FeatureEngineer(ch_client)

    df = await fe.get_hourly_features(device_id=None, hours=days * 24)

    logger.info(f"Fetched {len(df)} records from production")

    if df.empty:
        logger.warning("No data found. Make sure anomaly_ml.hourly_features materialized view is populated.")
        return np.array([]), np.array([]), np.array([])

    devices = df['device_id'].unique()
    all_features = []
    device_features_list = []

    logger.info(f"Computing features for {min(len(devices), 100)} devices...")

    for device_id in devices[:100]:
        device_df = df[df['device_id'] == device_id].copy()

        if len(device_df) < settings.WINDOW_SIZE:
            continue

        device_df = device_df.sort_values('hour')
        device_df = fe.compute_velocity_features(device_df)
        device_df = fe.compute_location_entropy(device_df)
        device_df = fe.compute_temporal_features(device_df)
        device_df = fe.compute_stationarity_score(device_df)
        device_df = fe.compute_statistical_features(device_df)
        device_df = fe.compute_rolling_features(device_df)
        device_df = fe.compute_autocorrelation_features(device_df)
        device_df = fe.compute_spatial_advanced_features(device_df)
        device_df = fe.compute_behavioral_patterns(device_df)

        device_df = AdvancedFeatureEngineer.compute_all_advanced_features(device_df)

        feature_cols = fe.get_feature_names(extended=True, advanced=True)

        available_cols = [col for col in feature_cols if col in device_df.columns]
        features = device_df[available_cols].values.astype(float)
        features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

        all_features.append(features)
        device_features_list.append(features)

    if not all_features:
        return np.array([]), np.array([]), np.array([])

    all_features_concat = np.concatenate(all_features, axis=0)
    global_mean = all_features_concat.mean(axis=0)
    global_std = all_features_concat.std(axis=0) + 1e-8

    logger.info(f"Global normalization stats computed from {len(all_features_concat)} samples")

    all_windows = []
    for features in device_features_list:
        features_norm = (features - global_mean) / global_std

        for j in range(len(features_norm) - settings.WINDOW_SIZE + 1):
            window = features_norm[j:j + settings.WINDOW_SIZE]
            all_windows.append(window)

    if not all_windows:
        return np.array([]), np.array([]), np.array([])

    data = np.array(all_windows)

    logger.info(f"Created {len(data)} training samples")
    logger.info(f"Shape: {data.shape}")
    logger.info(f"Features: {len(feature_cols)} (base: 20, extended: 50, advanced: 28 = 98 total)")
    logger.info(f"Advanced features: signal dynamics, network patterns, vendor behavior, cross-interactions")

    return data, global_mean, global_std


def train_model(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    epochs: int = 50,
    lr: float = 0.001,
    device: str = "cpu",
):
    """Обучение модели"""

    model = model.to(device)
    optimizer = optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    best_val_loss = float('inf')
    patience = 10
    patience_counter = 0

    logger.info("Starting training...")

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0

        for batch in train_loader:
            batch = batch.to(device)

            reconstructed = model(batch)
            loss = criterion(reconstructed, batch)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            train_loss += loss.item()

        train_loss /= max(1, len(train_loader))

        model.eval()
        val_loss = 0.0

        with torch.no_grad():
            for batch in val_loader:
                batch = batch.to(device)
                reconstructed = model(batch)
                loss = criterion(reconstructed, batch)
                val_loss += loss.item()

        val_loss /= max(1, len(val_loader))

        logger.info(f"Epoch {epoch + 1}/{epochs} - Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0

            Path('models').mkdir(exist_ok=True)
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'train_loss': train_loss,
                'val_loss': val_loss,
            }, 'models/tcn_model.pt')

            logger.info(f"  -> Best model saved (val_loss: {val_loss:.4f})")
        else:
            patience_counter += 1

            if patience_counter >= patience:
                logger.info(f"Early stopping at epoch {epoch + 1}")
                break

    logger.info(f"Training completed! Best val loss: {best_val_loss:.4f}")

    return model

async def main():
    """Training pipeline with production ClickHouse data (way_data)"""

    Path("models").mkdir(exist_ok=True)

    ch = ClickHouseClient()
    await ch.connect()

    try:
        logger.info("=" * 60)
        logger.info("Training TCN Autoencoder on PRODUCTION data")
        logger.info("Data source: santi.way_data via anomaly_ml.hourly_features")
        logger.info("=" * 60)

        data, global_mean, global_std = await prepare_training_data(ch, days=30)

        if data.size == 0:
            logger.error("No training data available!")
            logger.error("Possible reasons:")
            logger.error("1. No data in santi.way_data table")
            logger.error("2. anomaly_ml.hourly_features view not populated")
            logger.error("3. Not enough historical data (need at least 24 hours per device)")
            return

        n_features = data.shape[2]
        logger.info(f"Number of features: {n_features}")

        split_idx = int(len(data) * 0.85)
        train_data = data[:split_idx]
        val_data = data[split_idx:]

        logger.info(f"Train samples: {len(train_data)}")
        logger.info(f"Val samples: {len(val_data)}")

        train_dataset = TimeSeriesDataset(train_data)
        val_dataset = TimeSeriesDataset(val_data)

        train_loader = DataLoader(
            train_dataset,
            batch_size=settings.BATCH_SIZE,
            shuffle=True,
        )
        val_loader = DataLoader(
            val_dataset,
            batch_size=settings.BATCH_SIZE,
            shuffle=False,
        )

        model = TCN_Autoencoder(
            input_channels=n_features,
            hidden_channels=[64, 128, 256],
            kernel_size=3,
            dropout=0.2,
        )

        logger.info(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")

        model = train_model(
            model,
            train_loader,
            val_loader,
            epochs=50,
            lr=0.001,
            device=settings.DEVICE,
        )

        logger.info("Calculating anomaly threshold...")

        model.eval()
        all_scores: list[float] = []

        with torch.no_grad():
            for batch in val_loader:
                batch = batch.to(settings.DEVICE)
                scores = model.anomaly_score(batch).cpu().numpy()
                all_scores.extend(scores.tolist())

        threshold_95 = float(np.percentile(all_scores, 95))
        threshold_99 = float(np.percentile(all_scores, 99))

        logger.info(f"Threshold 95th percentile: {threshold_95:.4f}")
        logger.info(f"Threshold 99th percentile: {threshold_99:.4f}")

        metadata = {
            "thresholds": {
                "95": threshold_95,
                "99": threshold_99,
            },
            "train_samples": int(len(train_data)),
            "val_samples": int(len(val_data)),
            "input_channels": n_features,
            "window_size": settings.WINDOW_SIZE,
            "normalization": {
                "mean": global_mean.tolist(),
                "std": global_std.tolist(),
            },
            "data_source": "production_way_data",
            "feature_count": {
                "total": 98,
                "base": 20,
                "extended": 50,
                "advanced": 28
            },
            "feature_groups": [
                "base: event_count, signal strength, spatial, velocity, temporal, network_types",
                "extended: statistical, rolling, autocorrelation, spatial_advanced, behavioral",
                "advanced: signal_dynamics, network_patterns, vendor_behavior, cross_interactions"
            ]
        }

        with open('models/model_metadata.json', 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)

        logger.info("=" * 60)
        logger.info("Training completed successfully!")
        logger.info("=" * 60)
        logger.info(f"Model saved to: models/tcn_model.pt")
        logger.info(f"Metadata saved to: models/model_metadata.json")
        logger.info(f"Global normalization stats saved (mean, std for {n_features} features)")
        logger.info("Feature breakdown:")
        logger.info("  - Base features: 20 (signal, spatial, velocity, temporal, network)")
        logger.info("  - Extended features: +50 (statistical, rolling, autocorr, behavioral)")
        logger.info("  - Advanced features: +28 (signal dynamics, network patterns, vendor behavior)")
        logger.info("  - TOTAL: 98 features")
        logger.info("Ready for production inference on way_data")

    finally:
        await ch.disconnect()

if __name__ == "__main__":
    logger.info("SantiWay ML Training - Production Mode")
    logger.info("Using real data from ClickHouse way_data table")
    asyncio.run(main())
