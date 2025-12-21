import numpy as np
from typing import Dict, List, Any, Tuple
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import DBSCAN
from backend.services.clickhouse_client import ClickHouseClient
from backend.services.feature_engineer import FeatureEngineer
from loguru import logger

class DeviceComparison:
    """Service for comparing device behavior patterns"""

    def __init__(self, ch_client: ClickHouseClient):
        self.ch = ch_client
        self.feature_engineer = FeatureEngineer(ch_client)

    async def get_device_profiles(
        self,
        hours: int = 168,
        min_events: int = 50
    ) -> Dict[str, np.ndarray]:
        """Get behavioral profiles for all devices.

        Возвращает:
            Dictionary mapping device_id to feature vector"""
        query = f"""
        SELECT
            device_id,
            count() AS total_events,
            avg(activity_level) AS avg_activity,
            stddevPop(activity_level) AS std_activity,
            min(activity_level) AS min_activity,
            max(activity_level) AS max_activity,
            avg(lat) AS avg_lat,
            avg(lon) AS avg_lon,
            stddevPop(lat) AS std_lat,
            stddevPop(lon) AS std_lon,
            uniqExact(region) AS unique_regions,
            avg(toHour(timestamp)) AS avg_hour,
            countIf(toHour(timestamp) >= 0 AND toHour(timestamp) < 6) / count() AS night_ratio,
            countIf(toHour(timestamp) >= 9 AND toHour(timestamp) < 18) AS work_hours_events
        FROM events
        WHERE timestamp >= now() - INTERVAL {hours} HOUR
        GROUP BY device_id
        HAVING total_events >= {min_events}
        """

        result = await self.ch.query(query)

        profiles = {}
        for row in result:
            device_id = row['device_id']
            profile = np.array([
                float(row['avg_activity']),
                float(row['std_activity']),
                float(row['min_activity']),
                float(row['max_activity']),
                float(row['std_lat']),
                float(row['std_lon']),
                float(row['unique_regions']),
                float(row['avg_hour']),
                float(row['night_ratio']),
                float(row['work_hours_events']) / float(row['total_events'])
            ])
            profiles[device_id] = profile

        logger.info(f"Generated profiles for {len(profiles)} devices")
        return profiles

    async def find_similar_devices(
        self,
        device_id: str,
        hours: int = 168,
        top_k: int = 10,
        min_similarity: float = 0.8
    ) -> List[Dict[str, Any]]:
        """Find devices with similar behavior patterns.

        Аргументы:
            device_id: Target device to compare
            hours: Time window for analysis
            top_k: Maximum number of similar devices to return
            min_similarity: Minimum cosine similarity threshold

        Возвращает:
            List of similar devices with similarity scores"""
        profiles = await self.get_device_profiles(hours)

        if device_id not in profiles:
            logger.warning(f"Device {device_id} not found in profiles")
            return []

        target_profile = profiles[device_id].reshape(1, -1)

        similarities = []
        for other_id, other_profile in profiles.items():
            if other_id == device_id:
                continue

            sim = cosine_similarity(
                target_profile,
                other_profile.reshape(1, -1)
            )[0][0]

            if sim >= min_similarity:
                similarities.append({
                    'device_id': other_id,
                    'similarity': float(sim),
                    'profile': other_profile.tolist()
                })

        similarities.sort(key=lambda x: x['similarity'], reverse=True)

        return similarities[:top_k]

    async def detect_behavioral_clusters(
        self,
        hours: int = 168,
        eps: float = 0.3,
        min_samples: int = 2
    ) -> Dict[str, Any]:
        """Detect clusters of devices with similar behavior using DBSCAN.

        Аргументы:
            hours: Time window for analysis
            eps: DBSCAN epsilon parameter
            min_samples: Minimum samples per cluster

        Возвращает:
            Clustering results with device assignments"""
        profiles = await self.get_device_profiles(hours)

        if len(profiles) < min_samples:
            return {
                'clusters': [],
                'noise_devices': list(profiles.keys()),
                'num_clusters': 0
            }

        device_ids = list(profiles.keys())
        profile_matrix = np.array([profiles[d] for d in device_ids])

        profile_normalized = (profile_matrix - profile_matrix.mean(axis=0)) / (
            profile_matrix.std(axis=0) + 1e-8
        )

        clustering = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
        labels = clustering.fit_predict(profile_normalized)

        clusters = {}
        noise_devices = []

        for device_id, label in zip(device_ids, labels):
            if label == -1:
                noise_devices.append(device_id)
            else:
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(device_id)

        cluster_info = []
        for cluster_id, devices in clusters.items():
            cluster_profiles = np.array([profiles[d] for d in devices])
            centroid = cluster_profiles.mean(axis=0)

            cluster_info.append({
                'cluster_id': int(cluster_id),
                'devices': devices,
                'size': len(devices),
                'centroid': {
                    'avg_activity': float(centroid[0]),
                    'mobility': float(centroid[4] + centroid[5]),
                    'night_ratio': float(centroid[8]),
                    'work_ratio': float(centroid[9])
                }
            })

        cluster_info.sort(key=lambda x: x['size'], reverse=True)

        logger.info(
            f"Found {len(cluster_info)} clusters, "
            f"{len(noise_devices)} noise devices"
        )

        return {
            'clusters': cluster_info,
            'noise_devices': noise_devices,
            'num_clusters': len(cluster_info)
        }

    async def compare_two_devices(
        self,
        device_id_1: str,
        device_id_2: str,
        hours: int = 168
    ) -> Dict[str, Any]:
        """Detailed comparison between two specific devices.

        Возвращает:
            Comparison metrics and similarity analysis"""
        profiles = await self.get_device_profiles(hours)

        if device_id_1 not in profiles or device_id_2 not in profiles:
            missing = []
            if device_id_1 not in profiles:
                missing.append(device_id_1)
            if device_id_2 not in profiles:
                missing.append(device_id_2)
            return {'error': f'Devices not found: {missing}'}

        profile_1 = profiles[device_id_1]
        profile_2 = profiles[device_id_2]

        similarity = cosine_similarity(
            profile_1.reshape(1, -1),
            profile_2.reshape(1, -1)
        )[0][0]

        feature_names = [
            'avg_activity', 'std_activity', 'min_activity', 'max_activity',
            'std_lat', 'std_lon', 'unique_regions', 'avg_hour',
            'night_ratio', 'work_ratio'
        ]

        differences = {}
        for i, name in enumerate(feature_names):
            diff = abs(profile_1[i] - profile_2[i])
            rel_diff = diff / (max(abs(profile_1[i]), abs(profile_2[i])) + 1e-8)
            differences[name] = {
                'device_1': float(profile_1[i]),
                'device_2': float(profile_2[i]),
                'absolute_diff': float(diff),
                'relative_diff': float(rel_diff)
            }

        sorted_diffs = sorted(
            differences.items(),
            key=lambda x: x[1]['relative_diff'],
            reverse=True
        )
        most_different = [name for name, _ in sorted_diffs[:3]]

        return {
            'device_id_1': device_id_1,
            'device_id_2': device_id_2,
            'overall_similarity': float(similarity),
            'feature_comparison': differences,
            'most_different_features': most_different,
            'interpretation': self._interpret_comparison(similarity, most_different)
        }

    def _interpret_comparison(
        self,
        similarity: float,
        most_different: List[str]
    ) -> str:
        """Generate human-readable interpretation of comparison"""
        if similarity > 0.95:
            level = "very similar behavior patterns"
        elif similarity > 0.8:
            level = "similar behavior patterns"
        elif similarity > 0.6:
            level = "moderately similar behavior"
        else:
            level = "different behavior patterns"

        diff_explanations = {
            'avg_activity': 'activity levels',
            'std_activity': 'activity consistency',
            'night_ratio': 'night-time activity',
            'work_ratio': 'work-hours activity',
            'std_lat': 'north-south movement',
            'std_lon': 'east-west movement',
            'unique_regions': 'location diversity'
        }

        diff_texts = [
            diff_explanations.get(f, f)
            for f in most_different
        ]

        return (
            f"Devices show {level} (similarity: {similarity:.2f}). "
            f"Main differences in: {', '.join(diff_texts)}."
        )

    async def find_coordinated_devices(
        self,
        hours: int = 24,
        time_threshold_minutes: int = 5,
        distance_threshold_km: float = 0.5
    ) -> List[Dict[str, Any]]:
        """Find devices that appear to be coordinated (same place, same time).

        Возвращает:
            List of potentially coordinated device pairs"""
        query = f"""
        WITH device_locations AS (
            SELECT
                device_id,
                timestamp,
                lat,
                lon,
                region
            FROM events
            WHERE timestamp >= now() - INTERVAL {hours} HOUR
        )
        SELECT
            a.device_id AS device_1,
            b.device_id AS device_2,
            a.timestamp AS time_1,
            b.timestamp AS time_2,
            a.lat AS lat_1,
            a.lon AS lon_1,
            b.lat AS lat_2,
            b.lon AS lon_2,
            a.region,
            abs(toUnixTimestamp(a.timestamp) - toUnixTimestamp(b.timestamp)) AS time_diff_sec,
            sqrt(pow(a.lat - b.lat, 2) + pow(a.lon - b.lon, 2)) * 111 AS distance_km
        FROM device_locations a
        INNER JOIN device_locations b ON a.region = b.region
        WHERE a.device_id < b.device_id
        AND abs(toUnixTimestamp(a.timestamp) - toUnixTimestamp(b.timestamp)) <= {time_threshold_minutes * 60}
        AND sqrt(pow(a.lat - b.lat, 2) + pow(a.lon - b.lon, 2)) * 111 <= {distance_threshold_km}
        ORDER BY time_diff_sec, distance_km
        LIMIT 100
        """

        result = await self.ch.query(query)

        pair_counts = {}
        for row in result:
            pair = (row['device_1'], row['device_2'])
            if pair not in pair_counts:
                pair_counts[pair] = {
                    'device_1': row['device_1'],
                    'device_2': row['device_2'],
                    'encounters': 0,
                    'locations': []
                }

            pair_counts[pair]['encounters'] += 1
            pair_counts[pair]['locations'].append({
                'timestamp': str(row['time_1']),
                'region': row['region'],
                'distance_km': float(row['distance_km'])
            })

        coordinated = [
            info for info in pair_counts.values()
            if info['encounters'] >= 3
        ]

        coordinated.sort(key=lambda x: x['encounters'], reverse=True)

        logger.info(f"Found {len(coordinated)} potentially coordinated device pairs")

        return coordinated
