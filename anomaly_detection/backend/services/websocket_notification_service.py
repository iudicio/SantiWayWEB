import asyncio
import json
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from collections import deque
from loguru import logger

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
    from websockets.exceptions import ConnectionClosed, WebSocketException
except ImportError:
    logger.warning("websockets library not installed. Install: pip install websockets")
    websockets = None

from backend.utils.config import settings


class WebSocketNotificationService:
    """
    WebSocket клиент для отправки аномалий в Django

    Features:
    - Auto-reconnect с exponential backoff
    - Message buffering (если отключен)
    - Heartbeat/ping-pong
    - ACK механизм для подтверждения доставки
    """

    def __init__(self):
        django_url = settings.DJANGO_NOTIFICATION_URL
        ws_url = django_url.replace('http://', 'ws://').replace('https://', 'wss://')

        self.ws_url = f"{ws_url}/ws/ml-notifications/"
        self.ml_key = getattr(settings, 'ML_BACKEND_KEY', 'ml-secret-key-change-me')

        self.ws: Optional[WebSocketClientProtocol] = None
        self.connected = False
        self.reconnect_delay = 1
        self.max_reconnect_delay = 60

        self.message_queue = deque(maxlen=10000)

        self._reconnect_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info(f"WebSocket notification service initialized: {self.ws_url}")

    async def start(self):
        """Запуск сервиса"""
        if self._running:
            logger.warning("Service already running")
            return

        self._running = True

        await self.connect()

        self._reconnect_task = asyncio.create_task(self._reconnect_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info("WebSocket notification service started")

    async def stop(self):
        """Остановка сервиса"""
        self._running = False

        if self._reconnect_task:
            self._reconnect_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

        if self.ws:
            await self.ws.close()

        logger.info("WebSocket notification service stopped")

    async def connect(self):
        """Подключение к Django WebSocket"""
        try:
            if websockets is None:
                logger.error("websockets library not installed")
                return False

            self.ws = await websockets.connect(
                f"{self.ws_url}?ml_key={self.ml_key}",
                ping_interval=30,
                ping_timeout=10
            )

            self.connected = True
            self.reconnect_delay = 1

            msg = await self.ws.recv()
            data = json.loads(msg)

            if data.get('type') == 'system.connected':
                logger.info(f"Connected to Django WebSocket: {data.get('message')}")

                await self._flush_queue()
                return True
            else:
                logger.warning(f"Unexpected connection message: {data}")
                return False

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.connected = False
            return False

    async def _reconnect_loop(self):
        """Бесконечный цикл переподключения"""
        while self._running:
            if not self.connected:
                logger.info(f"Reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)

                success = await self.connect()

                if not success:
                    self.reconnect_delay = min(
                        self.reconnect_delay * 2,
                        self.max_reconnect_delay
                    )
            else:
                await asyncio.sleep(5)

    async def _heartbeat_loop(self):
        """Heartbeat для проверки соединения"""
        while self._running:
            await asyncio.sleep(30)

            if self.connected and self.ws:
                try:
                    await self.ws.send(json.dumps({"type": "ping"}))

                    try:
                        msg = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                        data = json.loads(msg)
                        if data.get('type') == 'pong':
                            logger.debug("Heartbeat OK")
                    except asyncio.TimeoutError:
                        logger.warning("Heartbeat timeout, connection may be dead")
                        self.connected = False

                except Exception as e:
                    logger.warning(f"Heartbeat failed: {e}")
                    self.connected = False

    async def send_anomaly_notification(
        self,
        api_key: str,
        anomaly: Dict[str, Any],
    ) -> bool:
        """
        Отправка уведомления об аномалии через WebSocket

        Args:
            api_key: API ключ пользователя
            anomaly: Словарь с данными аномалии

        Returns:
            bool: True если отправлено успешно
        """
        message = None 

        try:
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

            message = {
                'type': 'anomaly',
                'api_key': api_key,
                'payload': payload
            }

            if not self.connected:
                logger.warning("Not connected, queueing message")
                self.message_queue.append(message)
                return False

            await self.ws.send(json.dumps(message))

            try:
                ack_msg = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                ack_data = json.loads(ack_msg)

                if ack_data.get('type') == 'ack':
                    logger.info(
                        f"Anomaly sent and acknowledged: "
                        f"{anomaly_type} for {device_id} (score: {anomaly_score:.3f})"
                    )
                    return True
                elif ack_data.get('type') == 'error':
                    logger.error(f"Django error: {ack_data.get('message')}")
                    return False

            except asyncio.TimeoutError:
                logger.warning("ACK timeout, but message likely delivered")
                return True

            return True

        except ConnectionClosed:
            logger.error("Connection closed during send")
            self.connected = False
            if message is not None:
                self.message_queue.append(message)
            return False

        except Exception as e:
            logger.error(f"Failed to send anomaly notification: {e}")
            if message is not None:
                self.message_queue.append(message)
            return False

    async def _flush_queue(self):
        """
        Отправить буферизованные сообщения

        Если соединение разрывается во время отправки:
        1. Помечаем connected=False для триггера reconnect
        2. Возвращаем failed messages в начало очереди
        3. Reconnect loop автоматически повторит flush после переподключения
        """
        if not self.message_queue:
            return

        queue_size = len(self.message_queue)
        logger.info(f"Flushing {queue_size} queued messages")

        failed = []
        success_count = 0

        while self.message_queue and self.connected:
            message = self.message_queue.popleft()

            try:
                await self.ws.send(json.dumps(message))
                success_count += 1
                logger.debug(f"Flushed message {success_count}/{queue_size}")

            except ConnectionClosed as e:
                logger.warning(f"Connection closed during flush: {e}")
                failed.append(message)
                self.connected = False
                break

            except Exception as e:
                logger.error(f"Failed to flush message: {e}")
                failed.append(message)
                self.connected = False
                break

        for msg in reversed(failed):
            self.message_queue.appendleft(msg)

        if failed:
            logger.warning(
                f"Flush incomplete: {success_count}/{queue_size} sent, "
                f"{len(failed)} returned to queue. "
                f"Reconnect loop will retry after reconnection."
            )
        else:
            logger.info(f"Flush complete: {success_count}/{queue_size} messages sent")

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


_websocket_service: Optional[WebSocketNotificationService] = None


def get_websocket_notification_service() -> WebSocketNotificationService:
    """Получить singleton instance WebSocket сервиса"""
    global _websocket_service
    if _websocket_service is None:
        _websocket_service = WebSocketNotificationService()
    return _websocket_service


async def notify_anomalies_for_user_ws(
    api_key: str,
    anomalies: list[Dict[str, Any]],
) -> int:
    """
    Отправка аномалий через WebSocket

    Args:
        api_key: API ключ пользователя
        anomalies: Список аномалий

    Returns:
        int: Количество отправленных уведомлений
    """
    service = get_websocket_notification_service()

    if not service._running:
        await service.start()

    success_count = 0
    for anomaly in anomalies:
        result = await service.send_anomaly_notification(api_key, anomaly)
        if result:
            success_count += 1

    logger.info(f"Sent {success_count}/{len(anomalies)} anomalies via WebSocket")

    return success_count
