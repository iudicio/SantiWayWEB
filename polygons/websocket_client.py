#!/usr/bin/env python3
"""
Python WebSocket клиент для тестирования системы уведомлений
Этот клиент демонстрирует, как подключаться к WebSocket серверу и получать уведомления.

Использование:
    python websocket_client.py --api-key YOUR_API_KEY --host localhost:8000

Или для пользователя с session auth:
    python websocket_client.py --host localhost:8000 --session-id YOUR_SESSION_ID
"""

import argparse
import asyncio
import json
import logging
import signal
import sys
from datetime import datetime
from typing import Optional

import websockets

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class NotificationWebSocketClient:
    """WebSocket клиент для получения уведомлений о аномалиях"""

    def __init__(
        self,
        host: str,
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        ssl: bool = False,
    ):
        """
        Инициализация клиента

        Args:
            host: хост и порт сервера (например: localhost:8000)
            api_key: API ключ для аутентификации
            session_id: Session ID для аутентификации (альтернатива API ключу)
            ssl: использовать ли SSL (wss://)
        """
        self.host = host
        self.api_key = api_key
        self.session_id = session_id
        self.ssl = ssl
        self.websocket = None
        self.running = False
        self.reconnect_delay = 5  # 5 секунд
        self.max_reconnect_delay = 60
        self.ping_interval = 30  # 30 секунд

        self.notifications_received = 0
        self.connection_attempts = 0
        self.last_ping_time = None

    def get_websocket_url(self) -> str:
        """Формирует URL для WebSocket подключения"""
        protocol = "wss" if self.ssl else "ws"
        url = f"{protocol}://{self.host}/ws/notifications/"

        if self.api_key:
            url += f"?api_key={self.api_key}"

        return url

    async def connect(self):
        """Подключение к WebSocket серверу"""
        url = self.get_websocket_url()
        logger.info(f"Подключение к {url}...")

        try:
            connect_kwargs = {"ping_interval": 20, "ping_timeout": 10}

            if self.session_id and sys.platform != "win32":
                connect_kwargs["extra_headers"] = {
                    "Cookie": f"sessionid={self.session_id}"
                }

            self.websocket = await websockets.connect(url, **connect_kwargs)
            self.connection_attempts += 1
            logger.info(f"✓ Подключено! (попытка #{self.connection_attempts})")
            return True
        except Exception as e:
            logger.error(f"✗ Ошибка подключения: {e}")
            return False

    async def send_ping(self):
        """Отправка ping сообщения для поддержания соединения"""
        if self.websocket:
            try:
                await self.websocket.send(
                    json.dumps(
                        {"type": "ping", "timestamp": datetime.now().isoformat()}
                    )
                )
                self.last_ping_time = datetime.now()
                logger.debug("Отправлен ping")
            except Exception as e:
                logger.error(f"Ошибка отправки ping: {e}")

    async def mark_as_read(self, notification_id: str):
        """Отметить уведомление как прочитанное"""
        if self.websocket:
            try:
                await self.websocket.send(
                    json.dumps(
                        {"type": "mark_as_read", "notification_id": notification_id}
                    )
                )
                logger.info(
                    f"Отправлен запрос на отметку уведомления {notification_id} как прочитанного"
                )
            except Exception as e:
                logger.error(f"Ошибка отметки уведомления: {e}")

    async def request_pending_notifications(self):
        """Запросить все непрочитанные уведомления"""
        if self.websocket:
            try:
                await self.websocket.send(json.dumps({"type": "request_pending"}))
                logger.info("Запрошены непрочитанные уведомления")
            except Exception as e:
                logger.error(f"Ошибка запроса уведомлений: {e}")

    async def handle_message(self, message: str):
        """Обработка входящего сообщения"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "connection_established":
                logger.info("═" * 60)
                logger.info(f"🔗 Соединение установлено!")
                logger.info(f"   User ID: {data.get('user_id')}")
                logger.info(f"   Timestamp: {data.get('timestamp')}")
                logger.info("═" * 60)

                await self.request_pending_notifications()

            elif msg_type == "pong":
                logger.debug(f"Получен pong: {data.get('timestamp')}")

            elif msg_type == "notification":
                self.notifications_received += 1
                notification = data.get("notification", {})

                logger.info("╔" + "═" * 58 + "╗")
                logger.info(f"║ 🚨 НОВОЕ УВЕДОМЛЕНИЕ #{self.notifications_received}")
                logger.info("╠" + "═" * 58 + "╣")
                logger.info(f"║ ID: {notification.get('id')}")
                logger.info(f"║ Заголовок: {notification.get('title')}")
                logger.info(f"║ Сообщение: {notification.get('message')}")
                logger.info(f"║ Уровень: {notification.get('severity')}")
                logger.info(f"║ Тип: {notification.get('anomaly_type')}")
                logger.info(f"║ Полигон: {notification.get('polygon_name')}")
                logger.info(f"║ Устройство: {notification.get('device_id')}")
                logger.info(f"║ Время: {notification.get('created_at')}")
                logger.info("╚" + "═" * 58 + "╝")

                asyncio.create_task(self._auto_mark_read(notification.get("id")))

            elif msg_type == "pending_notifications":
                notifications = data.get("notifications", [])
                count = data.get("count", 0)

                logger.info("═" * 60)
                logger.info(f"📬 Получено {count} непрочитанных уведомлений")
                logger.info("═" * 60)

                for i, notif in enumerate(notifications, 1):
                    logger.info(f"\n[{i}/{count}] {notif.get('title')}")
                    logger.info(f"  └─ {notif.get('message')}")
                    logger.info(
                        f"  └─ Уровень: {notif.get('severity')} | Полигон: {notif.get('polygon_name')}"
                    )
                    logger.info(f"  └─ ID: {notif.get('id')}")

                if count == 0:
                    logger.info("✓ Нет непрочитанных уведомлений")

                logger.info("═" * 60)

            elif msg_type == "notification_marked":
                notification_id = data.get("notification_id")
                success = data.get("success")
                if success:
                    logger.info(
                        f"✓ Уведомление {notification_id} отмечено как прочитанное"
                    )
                else:
                    logger.warning(
                        f"✗ Не удалось отметить уведомление {notification_id}"
                    )

            elif msg_type == "error":
                logger.error(f"❌ Ошибка от сервера: {data.get('message')}")

            else:
                logger.warning(f"Неизвестный тип сообщения: {msg_type}")
                logger.debug(f"Данные: {data}")

        except json.JSONDecodeError:
            logger.error(f"Ошибка декодирования JSON: {message}")
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")

    async def _auto_mark_read(self, notification_id: str, delay: int = 2):
        """Автоматически отметить уведомление как прочитанное через delay секунд"""
        await asyncio.sleep(delay)
        await self.mark_as_read(notification_id)

    async def ping_loop(self):
        """Периодическая отправка ping для поддержания соединения"""
        while self.running:
            await asyncio.sleep(self.ping_interval)
            if self.running:
                await self.send_ping()

    async def listen(self):
        """Основной цикл прослушивания сообщений"""
        while self.running:
            try:
                if not self.websocket:
                    connected = await self.connect()
                    if not connected:
                        logger.warning(
                            f"Повторное подключение через {self.reconnect_delay} секунд..."
                        )
                        await asyncio.sleep(self.reconnect_delay)
                        self.reconnect_delay = min(
                            self.reconnect_delay * 1.5, self.max_reconnect_delay
                        )
                        continue

                    self.reconnect_delay = 5

                async for message in self.websocket:
                    await self.handle_message(message)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("⚠ Соединение закрыто сервером")
                self.websocket = None

            except Exception as e:
                logger.error(f"Ошибка в цикле прослушивания: {e}")
                await asyncio.sleep(5)

    async def run(self):
        """Запуск клиента"""
        self.running = True

        logger.info("╔" + "═" * 58 + "╗")
        logger.info("║  WebSocket Client для системы уведомлений SantiWay      ║")
        logger.info("╚" + "═" * 58 + "╝")
        logger.info("")

        try:
            await asyncio.gather(self.listen(), self.ping_loop())
        except asyncio.CancelledError:
            logger.info("Остановка клиента...")
        finally:
            await self.stop()

    async def stop(self):
        """Остановка клиента"""
        self.running = False
        if self.websocket:
            try:
                await self.websocket.close()
            except:
                pass

        logger.info("")
        logger.info("═" * 60)
        logger.info(f"Статистика:")
        logger.info(f"  • Получено уведомлений: {self.notifications_received}")
        logger.info(f"  • Попыток подключения: {self.connection_attempts}")
        logger.info("═" * 60)
        logger.info("Отключено от сервера")


async def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(
        description="WebSocket клиент для получения уведомлений SantiWay"
    )
    parser.add_argument(
        "--host",
        default="localhost:8000",
        help="Хост и порт сервера (по умолчанию: localhost:8000)",
    )
    parser.add_argument("--api-key", help="API ключ для аутентификации")
    parser.add_argument(
        "--session-id", help="Session ID для аутентификации (альтернатива API ключу)"
    )
    parser.add_argument("--ssl", action="store_true", help="Использовать SSL (wss://)")
    parser.add_argument(
        "--debug", action="store_true", help="Включить debug логирование"
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.api_key and not args.session_id:
        logger.error("Необходимо указать --api-key или --session-id для аутентификации")
        sys.exit(1)

    client = NotificationWebSocketClient(
        host=args.host, api_key=args.api_key, session_id=args.session_id, ssl=args.ssl
    )

    if sys.platform != "win32":
        loop = asyncio.get_event_loop()

        def signal_handler():
            logger.info("\nПолучен сигнал остановки...")
            asyncio.create_task(client.stop())

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

    try:
        await client.run()
    except KeyboardInterrupt:
        logger.info("\nПрервано пользователем")
    finally:
        await client.stop()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
