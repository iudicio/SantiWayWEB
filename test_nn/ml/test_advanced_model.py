"""
Тестирование продвинутой модели (TCN Advanced с extended features)
"""
import torch
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from backend.services.model_tcn_advanced import TCN_Autoencoder_Advanced, load_advanced_model
from backend.services.feature_engineer import FeatureEngineer
from backend.services.clickhouse_client import ClickHouseClient
from backend.utils.config import settings


async def test_advanced_model():
    """Тест продвинутой модели"""

    print("="*60)
    print("Testing Advanced TCN Model")
    print("="*60)

    metadata_path = Path('models/model_metadata_advanced.json')
    if not metadata_path.exists():
        print("Model metadata not found!")
        print("Please train the model first:")
        print("  python ml/train_advanced_model.py --days 3 --epochs 50 --use-extended --use-attention")
        return

    with open(metadata_path, 'r') as f:
        metadata = json.load(f)

    print(f"\nModel Info:")
    print(f"  Model type: {metadata['model_type']}")
    print(f"  Input channels: {metadata['input_channels']}")
    print(f"  Hidden channels: {metadata['hidden_channels']}")
    print(f"  Use attention: {metadata.get('use_attention', False)}")
    print(f"  Train samples: {metadata['train_samples']}")
    print(f"  Val samples: {metadata['val_samples']}")
    print(f"  Threshold 95th: {metadata['thresholds']['95']:.4f}")
    print(f"  Threshold 99th: {metadata['thresholds']['99']:.4f}")

    print(f"\nLoading model...")
    model_path = 'models/tcn_advanced_model.pt'

    if not Path(model_path).exists():
        print(f"Model file not found: {model_path}")
        return

    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    print(f"  Device: {device}")

    model = load_advanced_model(
        model_path=model_path,
        device=device,
        input_channels=metadata['input_channels'],
        use_attention=metadata.get('use_attention', True)
    )

    model_params = sum(p.numel() for p in model.parameters())
    print(f"  Parameters: {model_params:,}")

    print(f"\nConnecting to ClickHouse...")
    ch = ClickHouseClient()
    await ch.connect()

    try:
        print(f"\nLoading test data...")

        count_query = "SELECT count(*) as cnt FROM events"
        count_result = await ch.query(count_query)
        total_events = count_result[0]['cnt'] if count_result else 0

        if total_events == 0:
            print("No data in ClickHouse!")
            print("\nPlease load data first:")
            print("  clickhouse-client --database anomaly_demo \\")
            print("    --query=\"INSERT INTO events FORMAT CSVWithNames\" < data/train_events.csv")
            return

        print(f"  Total events in DB: {total_events:,}")

        global_mean = np.array(metadata['normalization']['mean'])
        global_std = np.array(metadata['normalization']['std'])

        fe = FeatureEngineer(ch, global_mean, global_std)

        devices_query = """
        SELECT device_id, count(*) as cnt
        FROM hourly_features
        WHERE hour >= now() - INTERVAL 72 HOUR
        GROUP BY device_id
        HAVING cnt >= 24
        ORDER BY cnt DESC
        LIMIT 10
        """
        devices_result = await ch.query(devices_query)

        if not devices_result:
            print("No devices with enough data (need 24+ hours)")
            print("\nTry using devices from events table directly")
            devices_query = "SELECT DISTINCT device_id FROM events LIMIT 20"
            devices_result = await ch.query(devices_query)
            if not devices_result:
                print("No devices found at all!")
                return

        test_devices = [row['device_id'] for row in devices_result]

        print(f"  Testing on {len(test_devices)} devices")

        all_scores = []
        all_device_scores = {}

        for device_id in test_devices:
            df = await fe.get_hourly_features(device_id, hours=72)

            if df.empty or len(df) < settings.WINDOW_SIZE:
                continue

            timeseries = fe.prepare_timeseries(
                df,
                settings.WINDOW_SIZE,
                use_extended_features=True
            )

            if len(timeseries) == 0:
                continue

            tensor = torch.FloatTensor(timeseries).permute(0, 2, 1).to(device)

            with torch.no_grad():
                scores = model.anomaly_score(tensor).cpu().numpy()

            all_scores.extend(scores.tolist())
            all_device_scores[device_id] = {
                'mean_score': float(scores.mean()),
                'max_score': float(scores.max()),
                'anomalies_95': int((scores > metadata['thresholds']['95']).sum()),
                'anomalies_99': int((scores > metadata['thresholds']['99']).sum()),
            }

            print(f"  {device_id}: mean={scores.mean():.4f}, max={scores.max():.4f}, "
                  f"anomalies_95={all_device_scores[device_id]['anomalies_95']}, "
                  f"anomalies_99={all_device_scores[device_id]['anomalies_99']}")

        all_scores = np.array(all_scores)

        if len(all_scores) == 0:
            print("\nNo scores computed - not enough data!")
            print("\nPossible reasons:")
            print("  1. No devices with 24+ hours of data")
            print("  2. hourly_features view is empty")
            print("  3. Data is too recent (materialized view not refreshed)")
            print("\nTry:")
            print("  1. Check data: clickhouse-client --database anomaly_demo --query=\"SELECT count(*) FROM events\"")
            print("  2. Check hourly_features: clickhouse-client --database anomaly_demo --query=\"SELECT count(*) FROM hourly_features\"")
            print("  3. Reload data if needed")
            return

        print(f"\nOverall Statistics:")
        print(f"  Total samples: {len(all_scores)}")
        print(f"  Mean score: {all_scores.mean():.4f}")
        print(f"  Std score: {all_scores.std():.4f}")
        print(f"  Min score: {all_scores.min():.4f}")
        print(f"  Max score: {all_scores.max():.4f}")
        print(f"  Median score: {np.median(all_scores):.4f}")
        print(f"  95th percentile: {np.percentile(all_scores, 95):.4f}")
        print(f"  99th percentile: {np.percentile(all_scores, 99):.4f}")

        anomalies_95 = (all_scores > metadata['thresholds']['95']).sum()
        anomalies_99 = (all_scores > metadata['thresholds']['99']).sum()

        print(f"\nAnomaly Detection:")
        print(f"  Anomalies (95th): {anomalies_95} ({100*anomalies_95/len(all_scores):.2f}%)")
        print(f"  Anomalies (99th): {anomalies_99} ({100*anomalies_99/len(all_scores):.2f}%)")

        print(f"\nCreating visualizations...")

        fig, axes = plt.subplots(2, 2, figsize=(12, 10))

        axes[0, 0].hist(all_scores, bins=50, alpha=0.7, color='blue', edgecolor='black')
        axes[0, 0].axvline(metadata['thresholds']['95'], color='orange',
                          linestyle='--', label='95th threshold')
        axes[0, 0].axvline(metadata['thresholds']['99'], color='red',
                          linestyle='--', label='99th threshold')
        axes[0, 0].set_xlabel('Anomaly Score')
        axes[0, 0].set_ylabel('Frequency')
        axes[0, 0].set_title('Score Distribution')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)

        axes[0, 1].plot(all_scores, alpha=0.6, linewidth=0.5)
        axes[0, 1].axhline(metadata['thresholds']['95'], color='orange',
                          linestyle='--', label='95th threshold')
        axes[0, 1].axhline(metadata['thresholds']['99'], color='red',
                          linestyle='--', label='99th threshold')
        axes[0, 1].set_xlabel('Sample Index')
        axes[0, 1].set_ylabel('Anomaly Score')
        axes[0, 1].set_title('Scores Over Time')
        axes[0, 1].legend()
        axes[0, 1].grid(True, alpha=0.3)

        device_names = list(all_device_scores.keys())
        anomalies_by_device = [all_device_scores[d]['anomalies_99'] for d in device_names]

        axes[1, 0].bar(range(len(device_names)), anomalies_by_device, color='red', alpha=0.7)
        axes[1, 0].set_xlabel('Device')
        axes[1, 0].set_ylabel('Anomalies (99th)')
        axes[1, 0].set_title('Anomalies per Device')
        axes[1, 0].set_xticks(range(len(device_names)))
        axes[1, 0].set_xticklabels([d[-4:] for d in device_names], rotation=45)
        axes[1, 0].grid(True, alpha=0.3, axis='y')

        axes[1, 1].boxplot(all_scores, vert=True)
        axes[1, 1].axhline(metadata['thresholds']['95'], color='orange',
                          linestyle='--', label='95th threshold')
        axes[1, 1].axhline(metadata['thresholds']['99'], color='red',
                          linestyle='--', label='99th threshold')
        axes[1, 1].set_ylabel('Anomaly Score')
        axes[1, 1].set_title('Score Distribution (Box Plot)')
        axes[1, 1].legend()
        axes[1, 1].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        output_path = 'models/test_advanced_results.png'
        plt.savefig(output_path, dpi=100, bbox_inches='tight')
        print(f"  Saved: {output_path}")

        print(f"\nTesting embedding extraction...")
        sample_tensor = torch.FloatTensor(timeseries[:5]).permute(0, 2, 1).to(device)
        with torch.no_grad():
            embeddings = model.get_embeddings(sample_tensor)
        print(f"  Embeddings shape: {embeddings.shape}")
        print(f"  Sample embedding: {embeddings[0][:5].cpu().numpy()}")

        print(f"\nTest completed successfully!")

    finally:
        await ch.disconnect()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_advanced_model())
