import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
import pandas as pd
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

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
    """Подготовка данных для обучения из ClickHouse с глобальной нормализацией"""

    print("Fetching data from ClickHouse...")

    fe = FeatureEngineer(ch_client)

    df = await fe.get_hourly_features(device_id=None, hours=days * 24)

    print(f"Fetched {len(df)} records")

    if df.empty:
        return np.array([]), np.array([]), np.array([])

    devices = df['device_id'].unique()
    all_features = []
    device_features_list = []

    print("Computing features for all devices...")

    for device_id in devices[:100]:
        device_df = df[df['device_id'] == device_id].copy()

        if len(device_df) < settings.WINDOW_SIZE:
            continue

        device_df = device_df.sort_values('hour')
        device_df = fe.compute_velocity_features(device_df)
        device_df = fe.compute_location_entropy(device_df)
        device_df = fe.compute_temporal_features(device_df)
        device_df = fe.compute_stationarity_score(device_df)

        feature_cols = [
            'event_count', 'avg_activity', 'std_activity', 'activity_range',
            'avg_lat', 'avg_lon', 'std_lat', 'std_lon',
            'velocity', 'acceleration', 'direction_change', 'velocity_std',
            'location_entropy', 'stationarity_score',
            'hour_sin', 'hour_cos', 'is_night',
        ]

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

    print(f"Global normalization stats computed from {len(all_features_concat)} samples")

    all_windows = []
    for features in device_features_list:
        features_norm = (features - global_mean) / global_std

        for j in range(len(features_norm) - settings.WINDOW_SIZE + 1):
            window = features_norm[j:j + settings.WINDOW_SIZE]
            all_windows.append(window)

    if not all_windows:
        return np.array([]), np.array([]), np.array([])

    data = np.array(all_windows)

    print(f"Created {len(data)} training samples")
    print(f"Shape: {data.shape}")

    return data, global_mean, global_std

def prepare_training_data_from_csv(csv_path: str, window_size: int = 24) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Подготовка данных из CSV файла (для локальной разработки)

    Эта функция агрегирует сырые события в hourly features,
    затем создаёт sliding windows для обучения.

    Возвращает:
        tuple: (windows, global_mean, global_std)"""

    print(f"Loading training data from {csv_path}...")
    df = pd.read_csv(csv_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    print(f"Loaded {len(df):,} events")

    df['hour'] = df['timestamp'].dt.floor('h')

    all_features = []
    device_features_list = []
    devices = df['device_id'].unique()

    print(f"Processing {len(devices)} devices...")

    for i, device_id in enumerate(devices):
        device_df = df[df['device_id'] == device_id].copy()

        hourly = device_df.groupby('hour').agg({
            'lat': ['mean', 'std'],
            'lon': ['mean', 'std'],
            'activity_level': ['mean', 'std', 'min', 'max', 'count'],
        }).reset_index()

        hourly.columns = [
            'hour', 'avg_lat', 'std_lat', 'avg_lon', 'std_lon',
            'avg_activity', 'std_activity', 'min_activity', 'max_activity', 'event_count'
        ]

        hourly = hourly.fillna(0)

        if len(hourly) < window_size:
            continue

        hourly['activity_range'] = hourly['max_activity'] - hourly['min_activity']

        from backend.services.feature_engineer import (
            haversine_distance, calculate_bearing
        )

        velocities = [0.0]
        for j in range(1, len(hourly)):
            dist = haversine_distance(
                hourly.iloc[j-1]['avg_lat'], hourly.iloc[j-1]['avg_lon'],
                hourly.iloc[j]['avg_lat'], hourly.iloc[j]['avg_lon']
            )
            velocities.append(dist)
        hourly['velocity'] = velocities

        bearings = [0.0]
        for j in range(1, len(hourly)):
            bearing = calculate_bearing(
                hourly.iloc[j-1]['avg_lat'], hourly.iloc[j-1]['avg_lon'],
                hourly.iloc[j]['avg_lat'], hourly.iloc[j]['avg_lon']
            )
            bearings.append(bearing)

        direction_changes = [0.0]
        for j in range(1, len(hourly)):
            change = abs(bearings[j] - bearings[j-1])
            if change > 180:
                change = 360 - change
            direction_changes.append(change)
        hourly['direction_change'] = direction_changes

        accelerations = [0.0]
        for j in range(1, len(hourly)):
            accelerations.append(velocities[j] - velocities[j-1])
        hourly['acceleration'] = accelerations

        hourly['velocity_std'] = pd.Series(velocities).rolling(window=3, min_periods=1).std().fillna(0).values

        hourly['location_entropy'] = hourly['std_lat'] + hourly['std_lon']

        stationarity = []
        for j in range(len(hourly)):
            start_idx = max(0, j - 3)
            window_vel = velocities[start_idx:j+1]
            score = max(0, 1 - sum(window_vel) / 0.5)
            stationarity.append(score)
        hourly['stationarity_score'] = stationarity

        hourly['hour_of_day'] = pd.to_datetime(hourly['hour']).dt.hour
        hourly['hour_sin'] = np.sin(2 * np.pi * hourly['hour_of_day'] / 24)
        hourly['hour_cos'] = np.cos(2 * np.pi * hourly['hour_of_day'] / 24)
        hourly['is_night'] = hourly['hour_of_day'].apply(lambda x: 1 if 0 <= x <= 6 else 0)

        feature_cols = [
            'event_count', 'avg_activity', 'std_activity', 'activity_range',
            'avg_lat', 'avg_lon', 'std_lat', 'std_lon',
            'velocity', 'acceleration', 'direction_change', 'velocity_std',
            'location_entropy', 'stationarity_score',
            'hour_sin', 'hour_cos', 'is_night',
        ]

        features = hourly[feature_cols].values.astype(float)
        features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

        all_features.append(features)
        device_features_list.append(features)

        if (i + 1) % 50 == 0:
            print(f"  Processed {i + 1}/{len(devices)} devices...")

    if not all_features:
        return np.array([]), np.array([]), np.array([])

    all_features_concat = np.concatenate(all_features, axis=0)
    global_mean = all_features_concat.mean(axis=0)
    global_std = all_features_concat.std(axis=0) + 1e-8

    print(f"Global normalization stats computed from {len(all_features_concat)} samples")

    all_windows = []
    for features in device_features_list:
        features_norm = (features - global_mean) / global_std

        for j in range(len(features_norm) - window_size + 1):
            window = features_norm[j:j + window_size]
            all_windows.append(window)

    if not all_windows:
        return np.array([]), np.array([]), np.array([])

    data = np.array(all_windows)
    print(f"Created {len(data)} training samples, shape: {data.shape}")

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

    print("\nStarting training...")

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

        print(f"Epoch {epoch + 1}/{epochs} - Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")

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

            print(f"  -> Best model saved (val_loss: {val_loss:.4f})")
        else:
            patience_counter += 1

            if patience_counter >= patience:
                print(f"\nEarly stopping at epoch {epoch + 1}")
                break

    print(f"\nTraining completed! Best val loss: {best_val_loss:.4f}")

    return model

async def main_clickhouse():
    """Training pipeline с ClickHouse"""

    Path("models").mkdir(exist_ok=True)

    ch = ClickHouseClient()
    await ch.connect()

    try:
        data, global_mean, global_std = await prepare_training_data(ch, days=5)

        if data.size == 0:
            print("No training data available. Please ingest data first.")
            return

        n_features = data.shape[2]
        print(f"\nNumber of features: {n_features}")

        split_idx = int(len(data) * 0.85)
        train_data = data[:split_idx]
        val_data = data[split_idx:]

        print(f"Train samples: {len(train_data)}")
        print(f"Val samples: {len(val_data)}")

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

        print(f"\nModel parameters: {sum(p.numel() for p in model.parameters()):,}")

        model = train_model(
            model,
            train_loader,
            val_loader,
            epochs=50,
            lr=0.001,
            device=settings.DEVICE,
        )

        print("\nCalculating anomaly threshold...")

        model.eval()
        all_scores: list[float] = []

        with torch.no_grad():
            for batch in val_loader:
                batch = batch.to(settings.DEVICE)
                scores = model.anomaly_score(batch).cpu().numpy()
                all_scores.extend(scores.tolist())

        threshold_95 = float(np.percentile(all_scores, 95))
        threshold_99 = float(np.percentile(all_scores, 99))

        print(f"Threshold 95th percentile: {threshold_95:.4f}")
        print(f"Threshold 99th percentile: {threshold_99:.4f}")

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
            }
        }

        import json
        with open('models/model_metadata.json', 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)

        print("\nTraining completed successfully!")
        print(f"Model saved to: models/tcn_model.pt")
        print(f"Metadata saved to: models/model_metadata.json")
        print(f"Global normalization stats saved (mean, std for {n_features} features)")

    finally:
        await ch.disconnect()

def main_csv():
    """Training pipeline с CSV файлами (без ClickHouse)"""

    Path("models").mkdir(exist_ok=True)

    train_path = "data/train_events.csv"
    if not Path(train_path).exists():
        print(f"Training data not found at {train_path}")
        print("Please run: python data/gen_data.py")
        return

    data, global_mean, global_std = prepare_training_data_from_csv(train_path, settings.WINDOW_SIZE)

    if data.size == 0:
        print("No training data created.")
        return

    n_features = data.shape[2]
    print(f"\nNumber of features: {n_features}")

    split_idx = int(len(data) * 0.85)
    train_data = data[:split_idx]
    val_data = data[split_idx:]

    print(f"Train samples: {len(train_data)}")
    print(f"Val samples: {len(val_data)}")

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

    print(f"\nModel parameters: {sum(p.numel() for p in model.parameters()):,}")

    model = train_model(
        model,
        train_loader,
        val_loader,
        epochs=50,
        lr=0.001,
        device=settings.DEVICE,
    )

    print("\nCalculating anomaly threshold...")

    model.eval()
    all_scores: list[float] = []

    with torch.no_grad():
        for batch in val_loader:
            batch = batch.to(settings.DEVICE)
            scores = model.anomaly_score(batch).cpu().numpy()
            all_scores.extend(scores.tolist())

    threshold_95 = float(np.percentile(all_scores, 95))
    threshold_99 = float(np.percentile(all_scores, 99))

    print(f"Threshold 95th percentile: {threshold_95:.4f}")
    print(f"Threshold 99th percentile: {threshold_99:.4f}")

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
        }
    }

    import json
    with open('models/model_metadata.json', 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)

    print("\nTraining completed successfully!")
    print(f"Model saved to: models/tcn_model.pt")
    print(f"Metadata saved to: models/model_metadata.json")
    print(f"Global normalization stats saved (mean, std for {n_features} features)")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Train TCN Autoencoder')
    parser.add_argument('--source', choices=['csv', 'clickhouse'], default='csv',
                        help='Data source: csv or clickhouse')

    args = parser.parse_args()

    if args.source == 'clickhouse':
        import asyncio
        asyncio.run(main_clickhouse())
    else:
        main_csv()
