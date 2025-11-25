import torch
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import sys
import json

sys.path.append(str(Path(__file__).parent.parent))

from backend.services.model_tcn import TCN_Autoencoder
from backend.services.feature_engineer import haversine_distance, calculate_bearing
from backend.utils.config import settings

def prepare_test_data_from_csv(csv_path: str, window_size: int = 24, global_mean: np.ndarray = None, global_std: np.ndarray = None):
    """Подготовка тестовых данных из CSV с сохранением меток аномалий

    Аргументы:
        csv_path: путь к CSV файлу
        window_size: размер окна
        global_mean: глобальное среднее из training данных
        global_std: глобальное std из training данных"""

    print(f"Loading test data from {csv_path}...")
    df = pd.read_csv(csv_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    if 'is_anomaly' in df.columns:
        df['is_anomaly'] = df['is_anomaly'].astype(str).str.lower() == 'true'

    print(f"Loaded {len(df):,} events")

    df['hour'] = df['timestamp'].dt.floor('h')

    all_windows = []
    all_labels = []
    all_anomaly_types = []
    all_device_ids = []

    devices = df['device_id'].unique()

    print(f"Processing {len(devices)} devices...")

    for i, device_id in enumerate(devices):
        device_df = df[df['device_id'] == device_id].copy()

        hourly = device_df.groupby('hour').agg({
            'lat': ['mean', 'std'],
            'lon': ['mean', 'std'],
            'activity_level': ['mean', 'std', 'min', 'max', 'count'],
            'is_anomaly': 'max',
            'anomaly_type': lambda x: ','.join(x.dropna().unique().astype(str)) if len(x.dropna()) > 0 else None,
        }).reset_index()

        hourly.columns = [
            'hour', 'avg_lat', 'std_lat', 'avg_lon', 'std_lon',
            'avg_activity', 'std_activity', 'min_activity', 'max_activity', 'event_count',
            'is_anomaly', 'anomaly_type'
        ]

        hourly = hourly.fillna(0)

        if len(hourly) < window_size:
            continue

        hourly['activity_range'] = hourly['max_activity'] - hourly['min_activity']

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

        if global_mean is not None and global_std is not None:
            features_norm = (features - global_mean) / global_std
        else:
            mean = features.mean(axis=0)
            std = features.std(axis=0) + 1e-8
            features_norm = (features - mean) / std

        for j in range(len(features_norm) - window_size + 1):
            window = features_norm[j:j + window_size]
            all_windows.append(window)

            window_data = hourly.iloc[j:j + window_size]
            has_anomaly = window_data['is_anomaly'].any()
            all_labels.append(has_anomaly)

            window_anomaly_types = window_data[window_data['is_anomaly'] == True]['anomaly_type'].dropna().unique()
            if len(window_anomaly_types) > 0:
                all_types = set()
                for atype in window_anomaly_types:
                    if atype:
                        all_types.update(str(atype).split(','))
                if all_types:
                    all_anomaly_types.append(list(all_types)[0])
                else:
                    all_anomaly_types.append(None)
            else:
                all_anomaly_types.append(None)

            all_device_ids.append(device_id)

        if (i + 1) % 50 == 0:
            print(f"  Processed {i + 1}/{len(devices)} devices...")

    if not all_windows:
        return np.array([]), np.array([]), [], []

    data = np.array(all_windows)
    labels = np.array(all_labels)

    print(f"Created {len(data)} test samples, shape: {data.shape}")
    print(f"Anomaly windows: {labels.sum()} / {len(labels)}")

    return data, labels, all_anomaly_types, all_device_ids

def test_model():
    """Тестирование модели на данных с аномалиями"""

    test_path = "data/test_events.csv"
    if not Path(test_path).exists():
        print(f"Test data not found at {test_path}")
        print("Please run: python data/gen_data.py")
        return

    print("Loading model metadata...")
    global_mean = None
    global_std = None
    try:
        with open('models/model_metadata.json', 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        n_features = metadata.get('input_channels', 17)
        threshold = metadata['thresholds']['95']
        threshold_95 = metadata['thresholds']['95']

        if 'normalization' in metadata:
            global_mean = np.array(metadata['normalization']['mean'])
            global_std = np.array(metadata['normalization']['std'])
            print(f"Loaded global normalization stats for {len(global_mean)} features")
        else:
            print("Warning: No normalization stats in metadata, using local normalization")
    except Exception as e:
        print(f"Warning: Could not load metadata: {e}")
        n_features = 17
        threshold = 0.1
        threshold_95 = 0.05

    print("Loading model...")
    model = TCN_Autoencoder(
        input_channels=n_features,
        hidden_channels=[64, 128, 256],
        kernel_size=3,
        dropout=0.2,
    )

    model_path = 'models/tcn_model.pt'
    if Path(model_path).exists():
        checkpoint = torch.load(model_path, map_location=settings.DEVICE)
        state_dict = (
            checkpoint['model_state_dict']
            if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint
            else checkpoint
        )
        model.load_state_dict(state_dict)
        print("Model loaded successfully")
    else:
        print(f"Warning: Model not found at {model_path}")

    model.eval()
    model = model.to(settings.DEVICE)

    data, labels, anomaly_types, device_ids = prepare_test_data_from_csv(
        test_path, settings.WINDOW_SIZE, global_mean, global_std
    )

    if data.size == 0:
        print("No test data created")
        return

    print("\nRunning inference...")
    tensor = torch.FloatTensor(data).permute(0, 2, 1).to(settings.DEVICE)

    with torch.no_grad():
        scores = model.anomaly_score(tensor).cpu().numpy()

    print("\n" + "="*60)
    print("ANOMALY DETECTION RESULTS")
    print("="*60)

    print(f"\nOverall Statistics:")
    print(f"  Total windows: {len(scores)}")
    print(f"  Mean score: {scores.mean():.4f}")
    print(f"  Std score: {scores.std():.4f}")
    print(f"  Min score: {scores.min():.4f}")
    print(f"  Max score: {scores.max():.4f}")
    print(f"  Threshold (95%): {threshold_95:.4f}")
    print(f"  Threshold (99%): {threshold:.4f}")

    predictions = scores > threshold
    predictions_95 = scores > threshold_95

    true_positives = np.sum(predictions & labels)
    false_positives = np.sum(predictions & ~labels)
    false_negatives = np.sum(~predictions & labels)
    true_negatives = np.sum(~predictions & ~labels)

    precision = true_positives / max(1, true_positives + false_positives)
    recall = true_positives / max(1, true_positives + false_negatives)
    f1 = 2 * precision * recall / max(1e-8, precision + recall)

    print(f"\nDetection Metrics (threshold 95%):")
    print(f"  True Positives: {true_positives}")
    print(f"  False Positives: {false_positives}")
    print(f"  False Negatives: {false_negatives}")
    print(f"  True Negatives: {true_negatives}")
    print(f"  Precision: {precision:.3f}")
    print(f"  Recall: {recall:.3f}")
    print(f"  F1 Score: {f1:.3f}")

    print(f"\nDetection by Anomaly Type:")
    anomaly_type_results = {}

    for i, atype in enumerate(anomaly_types):
        if atype is None:
            continue

        if atype not in anomaly_type_results:
            anomaly_type_results[atype] = {'total': 0, 'detected': 0, 'scores': []}

        anomaly_type_results[atype]['total'] += 1
        anomaly_type_results[atype]['scores'].append(scores[i])

        if predictions[i]:
            anomaly_type_results[atype]['detected'] += 1

    for atype, results in anomaly_type_results.items():
        detection_rate = results['detected'] / max(1, results['total'])
        avg_score = np.mean(results['scores'])
        print(f"  {atype}:")
        print(f"    Total: {results['total']}, Detected: {results['detected']}, Rate: {detection_rate:.1%}")
        print(f"    Avg Score: {avg_score:.4f}")

    normal_mask = ~labels
    normal_scores = scores[normal_mask]
    if len(normal_scores) > 0:
        print(f"\nNormal Data Statistics:")
        print(f"  Total normal windows: {len(normal_scores)}")
        print(f"  Mean score: {normal_scores.mean():.4f}")
        print(f"  False positive rate: {false_positives / max(1, len(normal_scores)):.1%}")

    print("\nGenerating plots...")
    Path('models').mkdir(exist_ok=True)

    try:
        plt.style.use('seaborn-v0_8-whitegrid')
    except Exception:
        try:
            plt.style.use('seaborn-whitegrid')
        except Exception:
            pass

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    ax1 = axes[0, 0]
    ax1.plot(scores, alpha=0.7, linewidth=0.5, label='Anomaly Score')
    ax1.axhline(y=threshold, color='r', linestyle='--', label=f'Threshold 99% ({threshold:.4f})')
    ax1.axhline(y=threshold_95, color='orange', linestyle='--', alpha=0.5, label=f'Threshold 95% ({threshold_95:.4f})')

    anomaly_indices = np.where(labels)[0]
    ax1.scatter(anomaly_indices, scores[anomaly_indices], color='red', s=10, alpha=0.5, label='Actual Anomalies')

    ax1.set_xlabel('Window Index')
    ax1.set_ylabel('Anomaly Score')
    ax1.set_title('Anomaly Scores with Ground Truth')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)

    ax2 = axes[0, 1]
    ax2.hist(scores[~labels], bins=50, alpha=0.7, label='Normal', color='blue', edgecolor='black')
    ax2.hist(scores[labels], bins=50, alpha=0.7, label='Anomaly', color='red', edgecolor='black')
    ax2.axvline(x=threshold, color='r', linestyle='--', label=f'Threshold 99%')
    ax2.set_xlabel('Anomaly Score')
    ax2.set_ylabel('Frequency')
    ax2.set_title('Score Distribution by Class')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    ax3 = axes[1, 0]
    if anomaly_type_results:
        types = list(anomaly_type_results.keys())
        rates = [anomaly_type_results[t]['detected'] / max(1, anomaly_type_results[t]['total']) for t in types]
        counts = [anomaly_type_results[t]['total'] for t in types]

        colors = plt.cm.Set2(np.linspace(0, 1, len(types)))

        bars = ax3.bar(range(len(types)), rates, color=colors, edgecolor='black', linewidth=0.5)
        ax3.set_xticks(range(len(types)))
        ax3.set_xticklabels([t.replace('_', '\n') for t in types], rotation=0, ha='center', fontsize=9)
        ax3.set_ylabel('Detection Rate')
        ax3.set_title('Detection Rate by Anomaly Type')
        ax3.set_ylim(0, 1.15)

        for i, (bar, rate, count) in enumerate(zip(bars, rates, counts)):
            ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.03,
                    f'{rate:.0%}\n(n={count})', ha='center', va='bottom', fontsize=8)
    else:
        ax3.text(0.5, 0.5, 'No anomalies detected', ha='center', va='center', transform=ax3.transAxes)
        ax3.set_title('Detection Rate by Anomaly Type')

    ax3.grid(True, alpha=0.3, axis='y')

    ax4 = axes[1, 1]
    thresholds_range = np.percentile(scores, np.arange(0, 101, 1))
    tprs = []
    fprs = []

    for thresh in thresholds_range:
        preds = scores > thresh
        tpr = np.sum(preds & labels) / max(1, labels.sum())
        fpr = np.sum(preds & ~labels) / max(1, (~labels).sum())
        tprs.append(tpr)
        fprs.append(fpr)

    ax4.plot(fprs, tprs, 'b-', linewidth=2)
    ax4.plot([0, 1], [0, 1], 'k--', alpha=0.3)
    ax4.set_xlabel('False Positive Rate')
    ax4.set_ylabel('True Positive Rate')
    ax4.set_title('ROC Curve')
    ax4.grid(True, alpha=0.3)

    auc = np.trapz(tprs[::-1], fprs[::-1])
    ax4.text(0.6, 0.2, f'AUC = {auc:.3f}', fontsize=12, bbox=dict(boxstyle='round', facecolor='wheat'))

    fig.suptitle('Anomaly Detection Model Evaluation', fontsize=14, fontweight='bold', y=1.02)

    plt.tight_layout()
    plt.savefig('models/test_results.png', dpi=150, bbox_inches='tight')
    print(f"Plot saved to: models/test_results.png")

    if anomaly_type_results:
        fig2, ax = plt.subplots(figsize=(10, 6))

        types = list(anomaly_type_results.keys())
        avg_scores = [np.mean(anomaly_type_results[t]['scores']) for t in types]
        std_scores = [np.std(anomaly_type_results[t]['scores']) for t in types]

        colors = plt.cm.Set2(np.linspace(0, 1, len(types)))
        bars = ax.bar(range(len(types)), avg_scores, yerr=std_scores,
                     color=colors, edgecolor='black', capsize=5)

        ax.axhline(y=threshold, color='r', linestyle='--', label=f'Threshold 99% ({threshold:.4f})')
        ax.axhline(y=threshold_95, color='orange', linestyle='--', alpha=0.7, label=f'Threshold 95%')

        ax.set_xticks(range(len(types)))
        ax.set_xticklabels([t.replace('_', '\n') for t in types], fontsize=9)
        ax.set_ylabel('Average Anomaly Score')
        ax.set_title('Average Anomaly Score by Type (with std)')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig('models/anomaly_scores_by_type.png', dpi=150, bbox_inches='tight')
        print(f"Additional plot saved to: models/anomaly_scores_by_type.png")

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total anomaly windows: {labels.sum()}")
    print(f"Detected anomalies: {true_positives}")
    print(f"Detection rate: {recall:.1%}")
    print(f"False alarm rate: {false_positives / max(1, (~labels).sum()):.1%}")
    print(f"AUC: {auc:.3f}")

if __name__ == "__main__":
    test_model()
