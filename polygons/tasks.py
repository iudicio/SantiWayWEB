"""
Celery задачи для работы с полигонами
"""

import logging

from django.utils import timezone

from celery import shared_task

from .models import Polygon, PolygonAction
from .utils import search_devices_in_polygon

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def monitor_mac_addresses(self, polygon_id, user_api_key, monitoring_interval=300):
    """
    Однотик мониторинга MAC-адресов: выполняет один проход и перепланирует себя,
    если действие остаётся в статусе running.
    """
    try:
        polygon = Polygon.objects.get(id=polygon_id)

        action, created = PolygonAction.objects.get_or_create(
            polygon=polygon,
            action_type="mac_monitoring",
            defaults={
                "parameters": {
                    "monitoring_interval": monitoring_interval,
                    "user_api_key": user_api_key,
                },
                "status": "running",
                "task_id": self.request.id,
                "started_at": timezone.now(),
            },
        )

        if not created:
            action.task_id = self.request.id
            if action.status != "running":
                logger.info(
                    f"Действие {action.id} не активно ({action.status}), пропускаем тик"
                )
                return
            action.save()

        devices = search_devices_in_polygon(polygon.geometry, user_api_key=user_api_key)

        mac_addresses = [
            d["mac"] for d in devices if isinstance(d, dict) and d.get("mac")
        ]

        action.parameters.update(
            {
                "last_check": timezone.now().isoformat(),
                "devices_found": len(devices),
                "mac_addresses": mac_addresses,
                "last_mac_count": len(mac_addresses),
            }
        )
        action.save()

        logger.info(
            f"Полигон {polygon.name}: найдено {len(mac_addresses)} MAC, перепланируем через {monitoring_interval}s"
        )

        # Перечитываем статус из БД перед перепланированием
        action_refreshed = (
            PolygonAction.objects.filter(id=action.id).only("status").first()
        )
        if action_refreshed and action_refreshed.status == "running":
            monitor_mac_addresses.apply_async(
                args=[str(polygon.id), user_api_key, monitoring_interval],
                countdown=int(monitoring_interval),
            )
        else:
            logger.info(
                f"Действие {action.id} остановлено со статусом {action_refreshed.status if action_refreshed else 'unknown'}"
            )

    except Polygon.DoesNotExist:
        logger.error(f"Полигон с ID {polygon_id} не найден")
        raise
    except Exception as e:
        logger.error(f"Критическая ошибка в задаче мониторинга: {e}")
        raise


@shared_task
def stop_polygon_monitoring(polygon_id):
    """Останавливает только мониторинг MAC для указанного полигона."""
    try:
        actions = PolygonAction.objects.filter(
            polygon_id=polygon_id, action_type="mac_monitoring", status="running"
        )
        from celery import current_app

        for action in actions:
            if action.task_id:
                current_app.control.revoke(action.task_id, terminate=True)
            action.status = "stopped"
            action.completed_at = timezone.now()
            action.save()
            logger.info(f"Остановлен мониторинг для полигона {action.polygon.name}")
    except Exception as e:
        logger.error(f"Ошибка при остановке мониторинга: {e}")
        raise


@shared_task
def stop_all_polygon_actions(polygon_id):
    """Универсальная остановка всех активных действий по полигону (running/pending/paused)."""
    try:
        qs = PolygonAction.objects.filter(
            polygon_id=polygon_id, status__in=["running", "pending", "paused"]
        )
        from celery import current_app

        for action in qs:
            if action.task_id:
                current_app.control.revoke(action.task_id, terminate=True)
            action.status = "stopped"
            action.completed_at = timezone.now()
            action.save()
            logger.info(
                f"Остановлено действие {action.action_type} для полигона {action.polygon_id}"
            )
    except Exception as e:
        logger.error(f"Ошибка при универсальной остановке действий: {e}")
        raise
