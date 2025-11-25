"""
Обучение продвинутой модели с расширенными features
"""
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
import pandas as pd
from pathlib import Path
import sys
import argparse
import json

sys.path.append(str(Path(__file__).parent.parent))

from backend.services.model_tcn_advanced import TCN_Autoencoder_Advanced
from backend.services.clickhouse_client import ClickHouseClient
from backend.services.feature_engineer import FeatureEngineer
from backend.utils.config import settings


class TimeSeriesDataset(Dataset):
    """Dataset для временных рядов"""

    def __init__(self, data: np.ndarray):
        """
        Аргументы:
            data: размерность (n_samples, window_size, n_features)
        """
        self.data = torch.FloatTensor(data)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        return self.data[idx].permute(1, 0)


async def prepare_training_data_extended(
    ch_client: ClickHouseClient,
    days: int = 30,
    use_extended_features: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Подготовка данных с расширенными features"""

    print(f"Fetching data from ClickHouse (use_extended_features={use_extended_features})...")

    fe = FeatureEngineer(ch_client)
    df = await fe.get_hourly_features(device_id=None, hours=days * 24)

    print(f"Fetched {len(df)} records")

    if df.empty:
        return np.array([]), np.array([]), np.array([])

    devices = df['device_id'].unique()
    all_features = []
    device_features_list = []

    print(f"Computing features for {min(100, len(devices))} devices...")

    for i, device_id in enumerate(devices[:100]):
        device_df = df[df['device_id'] == device_id].copy()

        if len(device_df) < settings.WINDOW_SIZE:
            continue

        device_df = device_df.sort_values('hour')

        device_df = fe.compute_velocity_features(device_df)
        device_df = fe.compute_location_entropy(device_df)
        device_df = fe.compute_temporal_features(device_df)
        device_df = fe.compute_stationarity_score(device_df)

        if use_extended_features:
            device_df = fe.compute_statistical_features(device_df)
            device_df = fe.compute_rolling_features(device_df)
            device_df = fe.compute_autocorrelation_features(device_df)
            device_df = fe.compute_spatial_advanced_features(device_df)
            device_df = fe.compute_behavioral_patterns(device_df)

        feature_cols = fe.get_feature_names(extended=use_extended_features)
        available_cols = [col for col in feature_cols if col in device_df.columns]

        features = device_df[available_cols].values.astype(float)
        features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

        all_features.append(features)
        device_features_list.append(features)

        if (i + 1) % 20 == 0:
            print(f"  Processed {i + 1}/{min(100, len(devices))} devices...")

    if not all_features:
        return np.array([]), np.array([]), np.array([])

    all_features_concat = np.concatenate(all_features, axis=0)
    global_mean = all_features_concat.mean(axis=0)
    global_std = all_features_concat.std(axis=0) + 1e-8

    print(f"Global normalization stats computed from {len(all_features_concat)} samples")
    print(f"Number of features: {len(global_mean)}")

    all_windows = []
    for features in device_features_list:
        features_norm = (features - global_mean) / global_std

        for j in range(len(features_norm) - settings.WINDOW_SIZE + 1):
            window = features_norm[j:j + settings.WINDOW_SIZE]
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
    save_path: str = "models/tcn_advanced_model.pt",
):
    """Обучение модели"""

    model = model.to(device)
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=5
    )
    criterion = nn.MSELoss()

    best_val_loss = float('inf')
    patience = 15
    patience_counter = 0

    print("\nStarting training...")
    print(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0

        for batch in train_loader:
            batch = batch.to(device)

            reconstructed = model(batch)
            loss = criterion(reconstructed, batch)

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
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

        scheduler.step(val_loss)

        print(f"Epoch {epoch + 1}/{epochs} - Train Loss: {train_loss:.6f}, Val Loss: {val_loss:.6f}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0

            Path(save_path).parent.mkdir(exist_ok=True)
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'train_loss': train_loss,
                'val_loss': val_loss,
            }, save_path)

            print(f"  Best model saved (val_loss: {val_loss:.6f})")
        else:
            patience_counter += 1

            if patience_counter >= patience:
                print(f"\nEarly stopping at epoch {epoch + 1}")
                break

    print(f"\nTraining completed! Best val loss: {best_val_loss:.6f}")

    return model


async def main():
    """Main training pipeline"""

    parser = argparse.ArgumentParser(description='Train Advanced TCN Autoencoder')
    parser.add_argument('--days', type=int, default=7, help='Days of data to use')
    parser.add_argument('--epochs', type=int, default=50, help='Number of epochs')
    parser.add_argument('--lr', type=float, default=0.001, help='Learning rate')
    parser.add_argument('--use-extended', action='store_true', default=True,
                        help='Use extended features (67 vs 17)')
    parser.add_argument('--use-attention', action='store_true', default=True,
                        help='Use attention mechanism')
    parser.add_argument('--device', type=str, default='cpu', help='Device (cpu/cuda)')

    args = parser.parse_args()

    Path("models").mkdir(exist_ok=True)

    ch = ClickHouseClient()
    await ch.connect()

    try:
        data, global_mean, global_std = await prepare_training_data_extended(
            ch, days=args.days, use_extended_features=args.use_extended
        )

        if data.size == 0:
            print("No training data available. Please ingest data first.")
            return

        n_features = data.shape[2]
        print(f"\n{'='*60}")
        print(f"Number of features: {n_features}")
        print(f"Extended features: {args.use_extended}")
        print(f"Attention: {args.use_attention}")
        print(f"{'='*60}\n")

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

        model = TCN_Autoencoder_Advanced(
            input_channels=n_features,
            hidden_channels=settings.HIDDEN_CHANNELS,
            kernel_size=settings.KERNEL_SIZE,
            dropout=settings.DROPOUT,
            use_attention=args.use_attention,
            num_attention_heads=settings.NUM_ATTENTION_HEADS,
        )

        print(f"\n{'='*60}")
        print(f"Model Architecture:")
        print(f"  Input channels: {n_features}")
        print(f"  Hidden channels: {settings.HIDDEN_CHANNELS}")
        print(f"  Kernel size: {settings.KERNEL_SIZE}")
        print(f"  Dropout: {settings.DROPOUT}")
        print(f"  Attention heads: {settings.NUM_ATTENTION_HEADS if args.use_attention else 'None'}")
        print(f"  Total parameters: {sum(p.numel() for p in model.parameters()):,}")
        print(f"{'='*60}\n")

        model = train_model(
            model,
            train_loader,
            val_loader,
            epochs=args.epochs,
            lr=args.lr,
            device=args.device,
            save_path='models/tcn_advanced_model.pt',
        )

        print("\nCalculating anomaly thresholds...")

        model.eval()
        all_scores: list[float] = []

        with torch.no_grad():
            for batch in val_loader:
                batch = batch.to(args.device)
                scores = model.anomaly_score(batch).cpu().numpy()
                all_scores.extend(scores.tolist())

        threshold_95 = float(np.percentile(all_scores, 95))
        threshold_99 = float(np.percentile(all_scores, 99))

        print(f"Threshold 95th percentile: {threshold_95:.4f}")
        print(f"Threshold 99th percentile: {threshold_99:.4f}")

        metadata = {
            "model_type": "tcn_advanced",
            "thresholds": {
                "95": threshold_95,
                "99": threshold_99,
            },
            "train_samples": int(len(train_data)),
            "val_samples": int(len(val_data)),
            "input_channels": n_features,
            "window_size": settings.WINDOW_SIZE,
            "hidden_channels": settings.HIDDEN_CHANNELS,
            "kernel_size": settings.KERNEL_SIZE,
            "use_attention": args.use_attention,
            "num_attention_heads": settings.NUM_ATTENTION_HEADS if args.use_attention else 0,
            "use_extended_features": args.use_extended,
            "normalization": {
                "mean": global_mean.tolist(),
                "std": global_std.tolist(),
            }
        }

        with open('models/model_metadata_advanced.json', 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)

        print(f"\n{'='*60}")
        print("Training completed successfully!")
        print(f"Model saved to: models/tcn_advanced_model.pt")
        print(f"Metadata saved to: models/model_metadata_advanced.json")
        print(f"Features: {n_features}")
        print(f"Parameters: {sum(p.numel() for p in model.parameters()):,}")
        print(f"{'='*60}")

    finally:
        await ch.disconnect()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
