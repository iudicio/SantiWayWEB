import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

def generate_realistic_trajectory(
    device_id: str,
    days: int = 7,
    pattern: Literal["commuter", "homebody", "active", "random"] = "commuter"
) -> pd.DataFrame:
    """
    Генерация реалистичной траектории устройства

    Patterns:
        - commuter: дом -> работа -> дом (будни), свободное движение (выходные)
        - homebody: в основном дома, редкие выходы
        - active: много перемещений в течение дня
        - random: случайное движение
    """

    home_lat = np.random.uniform(55.6, 55.9)
    home_lon = np.random.uniform(37.3, 37.8)

    work_lat = home_lat + np.random.uniform(-0.1, 0.1)
    work_lon = home_lon + np.random.uniform(-0.1, 0.1)

    places = [
        (home_lat + np.random.uniform(-0.05, 0.05), home_lon + np.random.uniform(-0.05, 0.05))
        for _ in range(3)
    ]

    start_time = datetime.now() - timedelta(days=days)
    events = []

    current_time = start_time
    while current_time < datetime.now():
        hour = current_time.hour
        weekday = current_time.weekday()

        if pattern == "commuter":
            if weekday < 5:
                if 0 <= hour < 8:
                    location = (home_lat, home_lon)
                    activity = np.random.normal(10, 3)
                elif 8 <= hour < 9:
                    progress = (hour - 8) + current_time.minute / 60
                    location = (
                        home_lat + (work_lat - home_lat) * progress,
                        home_lon + (work_lon - home_lon) * progress
                    )
                    activity = np.random.normal(60, 10)
                elif 9 <= hour < 18:
                    location = (work_lat, work_lon)
                    activity = np.random.normal(50, 15)
                elif 18 <= hour < 19:
                    progress = (hour - 18) + current_time.minute / 60
                    location = (
                        work_lat + (home_lat - work_lat) * progress,
                        work_lon + (home_lon - work_lon) * progress
                    )
                    activity = np.random.normal(60, 10)
                else:
                    location = (home_lat, home_lon)
                    activity = np.random.normal(30, 10)
            else:
                if np.random.random() < 0.3:
                    location = places[np.random.randint(len(places))]
                    activity = np.random.normal(50, 15)
                else:
                    location = (home_lat, home_lon)
                    activity = np.random.normal(20, 5)

        elif pattern == "homebody":
            if np.random.random() < 0.1 and 10 <= hour <= 20:
                location = places[np.random.randint(len(places))]
                activity = np.random.normal(40, 10)
            else:
                location = (home_lat, home_lon)
                activity = np.random.normal(15, 5) if 0 <= hour < 8 else np.random.normal(25, 8)

        elif pattern == "active":
            if 8 <= hour <= 22:
                if np.random.random() < 0.5:
                    location = places[np.random.randint(len(places))]
                elif np.random.random() < 0.3:
                    location = (work_lat, work_lon)
                else:
                    location = (home_lat, home_lon)
                activity = np.random.normal(60, 20)
            else:
                location = (home_lat, home_lon)
                activity = np.random.normal(10, 3)

        else:
            location = (
                home_lat + np.random.uniform(-0.05, 0.05),
                home_lon + np.random.uniform(-0.05, 0.05)
            )
            activity = np.random.normal(40, 15)

        n_events = np.random.poisson(5 if activity > 30 else 2)
        for _ in range(max(1, n_events)):
            events.append({
                'timestamp': current_time + timedelta(minutes=np.random.randint(0, 60)),
                'device_id': device_id,
                'lat': location[0] + np.random.normal(0, 0.002),
                'lon': location[1] + np.random.normal(0, 0.002),
                'activity_level': max(0, activity + np.random.normal(0, 5)),
                'region': 'Moscow',
                'is_anomaly': False,
                'anomaly_type': None,
            })

        current_time += timedelta(hours=1)

    return pd.DataFrame(events)

def inject_following_anomaly(
    target_device_id: str,
    follower_device_id: str,
    target_df: pd.DataFrame,
    duration_hours: int = 6,
    distance: float = 0.005,
) -> pd.DataFrame:
    """Паттерн слежки: follower следует за target

    Аргументы:
        target_device_id: ID цели
        follower_device_id: ID преследователя
        target_df: DataFrame с траекторией цели
        duration_hours: длительность слежки
        distance: дистанция следования (в градусах, ~0.001 = 100м)"""

    target_events = target_df[target_df['device_id'] == target_device_id].copy()
    if len(target_events) < duration_hours:
        return pd.DataFrame()

    start_idx = np.random.randint(0, len(target_events) - duration_hours)
    following_period = target_events.iloc[start_idx:start_idx + duration_hours * 5]

    events = []
    for _, row in following_period.iterrows():
        angle = np.random.uniform(0, 2 * np.pi)
        events.append({
            'timestamp': row['timestamp'] + timedelta(minutes=np.random.randint(1, 3)),
            'device_id': follower_device_id,
            'lat': row['lat'] + distance * np.cos(angle) + np.random.normal(0, 0.0005),
            'lon': row['lon'] + distance * np.sin(angle) + np.random.normal(0, 0.0005),
            'activity_level': np.random.normal(150, 20),
            'region': row['region'],
            'is_anomaly': True,
            'anomaly_type': 'following',
        })

    return pd.DataFrame(events)

def inject_relay_surveillance(
    target_device_id: str,
    target_df: pd.DataFrame,
    n_followers: int = 3,
    shift_hours: int = 2,
) -> pd.DataFrame:
    """
    Relay-слежка: несколько устройств по очереди следят за целью
    """

    target_events = target_df[target_df['device_id'] == target_device_id].copy()
    if len(target_events) < n_followers * shift_hours:
        return pd.DataFrame()

    all_events = []
    events_per_shift = len(target_events) // n_followers

    for i in range(n_followers):
        follower_id = f"relay_{target_device_id}_{i:02d}"
        start_idx = i * events_per_shift
        end_idx = (i + 1) * events_per_shift

        shift_events = target_events.iloc[start_idx:end_idx]

        for _, row in shift_events.iterrows():
            angle = np.random.uniform(0, 2 * np.pi)
            distance = np.random.uniform(0.003, 0.008)

            all_events.append({
                'timestamp': row['timestamp'] + timedelta(minutes=np.random.randint(1, 10)),
                'device_id': follower_id,
                'lat': row['lat'] + distance * np.cos(angle),
                'lon': row['lon'] + distance * np.sin(angle),
                'activity_level': np.random.normal(130, 25),
                'region': row['region'],
                'is_anomaly': True,
                'anomaly_type': 'relay_surveillance',
            })

    return pd.DataFrame(all_events)

def inject_stationary_surveillance(
    target_lat: float,
    target_lon: float,
    device_id: str,
    duration_hours: int = 8,
    start_time: datetime | None = None,
) -> pd.DataFrame:
    """
    Стационарное наблюдение: устройство "зависло" рядом с целью
    """

    if start_time is None:
        start_time = datetime.now() - timedelta(days=np.random.randint(1, 3))

    events = []
    current_time = start_time

    for _ in range(duration_hours):
        n_events = np.random.poisson(8)

        for _ in range(n_events):
            events.append({
                'timestamp': current_time + timedelta(minutes=np.random.randint(0, 60)),
                'device_id': device_id,
                'lat': target_lat + np.random.normal(0, 0.0002),
                'lon': target_lon + np.random.normal(0, 0.0002),
                'activity_level': np.random.normal(160, 25),
                'region': 'Moscow',
                'is_anomaly': True,
                'anomaly_type': 'stationary_surveillance',
            })

        current_time += timedelta(hours=1)

    return pd.DataFrame(events)

def inject_density_anomaly(
    center_lat: float = 55.7558,
    center_lon: float = 37.6173,
    n_devices: int = 50,
    start_time: datetime | None = None,
) -> pd.DataFrame:
    """
    Массовое скопление устройств в одной точке
    """

    if start_time is None:
        start_time = datetime.now() - timedelta(days=np.random.randint(1, 3))

    events = []
    for i in range(n_devices):
        device_id = f"cluster_{i:04d}"

        events.append({
            'timestamp': start_time + timedelta(minutes=np.random.randint(0, 30)),
            'device_id': device_id,
            'lat': center_lat + np.random.normal(0, 0.001),
            'lon': center_lon + np.random.normal(0, 0.001),
            'activity_level': np.random.normal(140, 20),
            'region': 'Moscow_Center',
            'is_anomaly': True,
            'anomaly_type': 'density_cluster',
        })

    return pd.DataFrame(events)

def inject_dispersion_anomaly(
    center_lat: float = 55.7558,
    center_lon: float = 37.6173,
    n_devices: int = 30,
    start_time: datetime | None = None,
) -> pd.DataFrame:
    """
    Резкое рассредоточение: устройства были вместе и резко разъехались
    """

    if start_time is None:
        start_time = datetime.now() - timedelta(days=np.random.randint(1, 3))

    events = []

    for i in range(n_devices):
        device_id = f"disperse_{i:04d}"

        for h in range(3):
            events.append({
                'timestamp': start_time + timedelta(hours=h, minutes=np.random.randint(0, 60)),
                'device_id': device_id,
                'lat': center_lat + np.random.normal(0, 0.002),
                'lon': center_lon + np.random.normal(0, 0.002),
                'activity_level': np.random.normal(120, 20),
                'region': 'Moscow',
                'is_anomaly': True,
                'anomaly_type': 'dispersion',
            })

        angle = 2 * np.pi * i / n_devices
        speed = np.random.uniform(0.02, 0.05)

        for h in range(3, 6):
            distance = speed * (h - 2)
            events.append({
                'timestamp': start_time + timedelta(hours=h, minutes=np.random.randint(0, 60)),
                'device_id': device_id,
                'lat': center_lat + distance * np.cos(angle),
                'lon': center_lon + distance * np.sin(angle),
                'activity_level': np.random.normal(150, 25),
                'region': 'Moscow',
                'is_anomaly': True,
                'anomaly_type': 'dispersion',
            })

    return pd.DataFrame(events)

def inject_night_activity_anomaly(
    device_id: str,
    n_nights: int = 3,
) -> pd.DataFrame:
    """
    Аномальная ночная активность
    """

    events = []

    for night in range(n_nights):
        night_time = datetime.now() - timedelta(days=night + 1, hours=-3)

        base_lat = np.random.uniform(55.6, 55.9)
        base_lon = np.random.uniform(37.3, 37.8)

        for _ in range(20):
            events.append({
                'timestamp': night_time + timedelta(minutes=np.random.randint(0, 120)),
                'device_id': device_id,
                'lat': base_lat + np.random.normal(0, 0.005),
                'lon': base_lon + np.random.normal(0, 0.005),
                'activity_level': np.random.normal(170, 30),
                'region': 'Moscow',
                'is_anomaly': True,
                'anomaly_type': 'night_activity',
            })

    return pd.DataFrame(events)

def generate_training_data(n_devices: int = 500, days: int = 3) -> pd.DataFrame:
    """
    Генерация ЧИСТЫХ данных для обучения (только нормальное поведение)
    """

    print(f"Generating CLEAN training data: {n_devices} devices, {days} days...")

    all_events = []
    patterns = ["commuter", "homebody", "active", "random"]
    pattern_weights = [0.5, 0.2, 0.2, 0.1]

    for i in range(n_devices):
        device_id = f"train_device_{i:04d}"
        pattern = np.random.choice(patterns, p=pattern_weights)

        df = generate_realistic_trajectory(device_id, days, pattern)
        all_events.append(df)

        if (i + 1) % 100 == 0:
            print(f"  Generated {i + 1}/{n_devices} devices...")

    full_df = pd.concat(all_events, ignore_index=True)
    full_df = full_df.sort_values('timestamp')

    print(f"\nTraining data generated:")
    print(f"  Total events: {len(full_df):,}")
    print(f"  Unique devices: {full_df['device_id'].nunique()}")
    print(f"  Anomalies: {full_df['is_anomaly'].sum()} (should be 0)")

    return full_df

def generate_test_data(n_normal_devices: int = 100, days: int = 3) -> pd.DataFrame:
    """
    Генерация тестовых данных с аномалиями
    """

    print(f"Generating TEST data with anomalies...")

    all_events = []

    print("  Generating normal devices...")
    patterns = ["commuter", "homebody", "active", "random"]

    for i in range(n_normal_devices):
        device_id = f"test_normal_{i:04d}"
        pattern = np.random.choice(patterns)
        df = generate_realistic_trajectory(device_id, days, pattern)
        all_events.append(df)

    print("  Injecting following patterns...")
    for i in range(20):
        target_id = f"target_{i:04d}"
        target_df = generate_realistic_trajectory(target_id, days, "commuter")
        all_events.append(target_df)

        follower_id = f"follower_{i:04d}"
        follower_df = inject_following_anomaly(target_id, follower_id, target_df, duration_hours=8)
        if not follower_df.empty:
            all_events.append(follower_df)

    print("  Injecting relay surveillance...")
    for i in range(15):
        target_id = f"relay_target_{i:04d}"
        target_df = generate_realistic_trajectory(target_id, days, "active")
        all_events.append(target_df)

        relay_df = inject_relay_surveillance(target_id, target_df, n_followers=3)
        if not relay_df.empty:
            all_events.append(relay_df)

    print("  Injecting stationary surveillance...")
    for i in range(20):
        lat = np.random.uniform(55.6, 55.9)
        lon = np.random.uniform(37.3, 37.8)

        df = inject_stationary_surveillance(lat, lon, f"watcher_{i:04d}", duration_hours=12)
        all_events.append(df)

    print("  Injecting density clusters...")
    for i in range(3):
        lat = np.random.uniform(55.7, 55.8)
        lon = np.random.uniform(37.5, 37.7)
        df = inject_density_anomaly(lat, lon, n_devices=40)
        all_events.append(df)

    print("  Injecting dispersion patterns...")
    for i in range(3):
        lat = np.random.uniform(55.7, 55.8)
        lon = np.random.uniform(37.5, 37.7)
        df = inject_dispersion_anomaly(lat, lon, n_devices=25)
        all_events.append(df)

    print("  Injecting night activity...")
    for i in range(5):
        df = inject_night_activity_anomaly(f"night_active_{i:04d}", n_nights=2)
        all_events.append(df)

    full_df = pd.concat(all_events, ignore_index=True)
    full_df = full_df.sort_values('timestamp')

    anomaly_counts = full_df[full_df['is_anomaly']]['anomaly_type'].value_counts()

    print(f"\nTest data generated:")
    print(f"  Total events: {len(full_df):,}")
    print(f"  Unique devices: {full_df['device_id'].nunique()}")
    print(f"  Normal events: {(~full_df['is_anomaly']).sum():,}")
    print(f"  Anomaly events: {full_df['is_anomaly'].sum():,}")
    print(f"\nAnomaly breakdown:")
    for atype, count in anomaly_counts.items():
        print(f"    {atype}: {count}")

    return full_df

if __name__ == "__main__":
    Path("data").mkdir(exist_ok=True)

    train_df = generate_training_data(n_devices=300, days=3)
    train_path = "data/train_events.csv"
    train_df.to_csv(train_path, index=False)
    print(f"\nTraining data saved to {train_path}")
    print(f"File size: {Path(train_path).stat().st_size / 1024 / 1024:.2f} MB")

    print("\n" + "="*60 + "\n")

    test_df = generate_test_data(n_normal_devices=30, days=3)
    test_path = "data/test_events.csv"
    test_df.to_csv(test_path, index=False)
    print(f"\nTest data saved to {test_path}")
    print(f"File size: {Path(test_path).stat().st_size / 1024 / 1024:.2f} MB")
