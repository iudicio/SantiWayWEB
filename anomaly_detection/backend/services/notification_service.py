import asyncio
import uuid
import re
import httpx
from typing import Dict, List, Any
from datetime import datetime
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from backend.utils.config import settings


class AnomalyNotificationService:
    """Сервис отправки аномалий через WebSocket (via Django HTTP API)"""

    def __init__(self):
        self.django_url = settings.DJANGO_NOTIFICATION_URL
        self.notification_endpoint = f"{self.django_url}/notifications/api/send/"
        logger.info(f"Notification service initialized with Django URL: {self.django_url}")

    async def health_check(self) -> bool:
        """
        Проверка доступности Django notification endpoint

        Returns:
            bool: True если Django доступен, False если нет
        """
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.django_url}/health", follow_redirects=True)

                if response.status_code in (200, 404):  
                    logger.info(f"Django notification service is available at {self.django_url}")
                    return True
                else:
                    logger.warning(
                        f"Django responded with status {response.status_code}, "
                        f"notifications may not work properly"
                    )
                    return False

        except (httpx.HTTPError, httpx.TimeoutException, ConnectionError) as e:
            logger.error(f"Django notification service health check failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during Django health check: {e}")
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException, ConnectionError)),
        before_sleep=before_sleep_log(logger, logger.level("WARNING").no)
    )
    async def send_anomaly_notification(
        self,
        api_key: str,
        anomaly: Dict[str, Any],
    ) -> bool:
        """
        Отправка уведомления об аномалии через WebSocket с retry logic

        Retry strategy:
        - Max attempts: 3
        - Exponential backoff: 1s -> 2s -> 4s -> 10s
        - Retry on: HTTPError, TimeoutException, ConnectionError

        Args:
            api_key: API ключ пользователя
            anomaly: Словарь с данными аномалии

        Returns:
            bool: True если отправлено успешно
        """
        try:
            group_name = self._sanitize_group(f"api_{api_key}")

            device_id = anomaly.get('device_id', '')
            anomaly_type = anomaly.get('anomaly_type', 'unknown')
            anomaly_score = float(anomaly.get('anomaly_score', 0))
            timestamp = anomaly.get('timestamp')
            folder_name = anomaly.get('folder_name', '')
            vendor = anomaly.get('vendor', '')
            network_type = anomaly.get('network_type', '')
            details = anomaly.get('details', {})

            title, text, severity = self._get_notification_content(
                anomaly_type, anomaly_score, device_id, vendor, folder_name
            )

            coords = {}
            if 'avg_lat' in details and 'avg_lon' in details:
                coords = {
                    'lat': details['avg_lat'],
                    'lon': details['avg_lon']
                }

            payload = {
                'type': 'anomaly.detected',
                'notif_id': str(uuid.uuid4()),
                'ts': timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                'severity': severity,
                'title': title,
                'text': text,
                'anomaly': {
                    'device_id': device_id,
                    'type': anomaly_type,
                    'score': round(anomaly_score, 3),
                    'folder': folder_name,
                    'vendor': vendor,
                    'network_type': network_type,
                    'details': details,
                },
                'coords': coords,
            }

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    self.notification_endpoint,
                    json={
                        'api_key': api_key,
                        'payload': payload,
                    }
                )

                if response.status_code == 200:
                    logger.info(
                        f"Anomaly notification sent via Django API: "
                        f"{anomaly_type} for {device_id} (score: {anomaly_score:.3f})"
                    )
                    return True
                else:
                    logger.error(f"Failed to send notification: HTTP {response.status_code}")
                    return False

        except Exception as e:
            logger.error(f"Failed to send anomaly notification: {e}")
            return False

    async def send_batch_anomalies(
        self,
        api_key: str,
        anomalies: List[Dict[str, Any]],
    ) -> int:
        """
        Отправка batch аномалий

        Args:
            api_key: API ключ пользователя
            anomalies: Список аномалий

        Returns:
            int: Количество успешно отправленных
        """
        tasks = [
            self.send_anomaly_notification(api_key, anomaly)
            for anomaly in anomalies
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if r is True)
        logger.info(f"Batch sent: {success_count}/{len(anomalies)} anomalies")

        return success_count

    def _sanitize_group(self, name: str) -> str:
        """Sanitize group name для channels"""
        return re.sub(r"[^0-9A-Za-z._-]", "_", name)[:99]

    def _get_notification_content(
        self,
        anomaly_type: str,
        score: float,
        device_id: str,
        vendor: str,
        folder: str,
    ) -> tuple[str, str, str]:
        """
        Генерация заголовка и текста уведомления

        Returns:
            tuple: (title, text, severity)
        """
        if score > 0.8:
            severity = 'critical'
        elif score > 0.5:
            severity = 'warning'
        else:
            severity = 'info'

        type_names = {
            'density_spike': 'Скопление устройств',
            'time_anomaly': 'Активность в необычное время',
            'personal_deviation': 'Аномальное поведение устройства',
            'spatial_outlier': 'Пространственная аномалия',
            'night_activity': 'Ночная активность',
            'following': 'Подозрение на слежку',
            'stationary_surveillance': 'Стационарное наблюдение',
            'signal_anomaly': 'Аномалия сигнала',
        }

        type_name = type_names.get(anomaly_type, anomaly_type)

        title = f"{type_name}"
        if severity == 'critical':
            title = f"КРИТИЧНО: {type_name}"

        parts = []
        if device_id:
            parts.append(f"Устройство: {device_id[:8]}...")
        if vendor:
            parts.append(f"Производитель: {vendor}")
        if folder:
            parts.append(f"Папка: {folder}")
        parts.append(f"Оценка аномальности: {score:.1%}")

        text = " | ".join(parts)

        return title, text, severity


_notification_service = None


def get_notification_service() -> AnomalyNotificationService:
    """Получить singleton instance сервиса"""
    global _notification_service
    if _notification_service is None:
        _notification_service = AnomalyNotificationService()
    return _notification_service


async def notify_anomalies_for_user(
    api_key: str,
    anomalies: List[Dict[str, Any]],
) -> int:
    """
    Convenience функция для отправки аномалий пользователю

    Args:
        api_key: API ключ пользователя
        anomalies: Список аномалий

    Returns:
        int: Количество отправленных уведомлений
    """
    service = get_notification_service()
    return await service.send_batch_anomalies(api_key, anomalies)
