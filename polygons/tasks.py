"""
Celery задачи для работы с полигонами
"""

import logging

from django.utils import timezone

from celery import shared_task
from .models import Polygon, PolygonAction, AnomalyDetection, Notification, NotificationTarget
from .utils import search_devices_in_polygon
import logging
import json
from typing import List, Dict, Any
from collections import defaultdict

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

        mac_addresses = []
        for d in devices:
            if isinstance(d, dict):
                mac = d.get('device_id') or d.get('mac') or d.get('user_phone_mac')
                if mac:
                    mac_addresses.append(mac)

        anomalies_detected = detect_anomalies_in_devices.delay(
            str(action.id), 
            devices, 
            action.parameters.get('previous_devices', [])
        )

        action.parameters.update({
            'last_check': timezone.now().isoformat(),
            'devices_found': len(devices),
            'mac_addresses': mac_addresses,
            'last_mac_count': len(mac_addresses),
            'previous_devices': devices  
        })
        action.save()

        logger.info(
            f"Полигон {polygon.name}: найдено {len(mac_addresses)} MAC, перепланируем через {monitoring_interval}s"
        )

        action_refreshed = PolygonAction.objects.filter(id=action.id).only('status').first()
        if action_refreshed and action_refreshed.status == 'running':
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


@shared_task
def detect_anomalies_in_devices(action_id: str, current_devices: List[Dict[str, Any]], previous_devices: List[Dict[str, Any]]):
    """
    Обнаруживает аномалии в устройствах полигона
    """
    try:
        action = PolygonAction.objects.get(id=action_id)
        
        current_devices_dict = {d.get('device_id', d.get('mac', '')): d for d in current_devices if isinstance(d, dict)}
        previous_devices_dict = {d.get('device_id', d.get('mac', '')): d for d in previous_devices if isinstance(d, dict)}
        
        anomalies_found = []
        
        # 1. Обнаружение новых устройств
        for device_id, device in current_devices_dict.items():
            if device_id and device_id not in previous_devices_dict:
                anomaly = create_anomaly(
                    action=action,
                    anomaly_type='new_device',
                    severity='medium',
                    device_id=device_id,
                    device_data=device,
                    description=f"Обнаружено новое устройство: {device_id}"
                )
                anomalies_found.append(anomaly)
        
        # 2. Обнаружение аномалий сигнала
        for device_id, device in current_devices_dict.items():
            if device_id in previous_devices_dict:
                prev_device = previous_devices_dict[device_id]
                current_signal = device.get('signal_strength', 0)
                prev_signal = prev_device.get('signal_strength', 0)
                
                if abs(current_signal - prev_signal) > 30:
                    anomaly = create_anomaly(
                        action=action,
                        anomaly_type='signal_anomaly',
                        severity='low',
                        device_id=device_id,
                        device_data=device,
                        description=f"Резкое изменение сигнала: {prev_signal} -> {current_signal} dBm",
                        metadata={
                            'previous_signal': prev_signal,
                            'current_signal': current_signal,
                            'signal_diff': abs(current_signal - prev_signal)
                        }
                    )
                    anomalies_found.append(anomaly)
        
        # 3. Обнаружение неизвестных производителей
        for device_id, device in current_devices_dict.items():
            vendor = device.get('vendor', '').lower()
            if vendor in ['unknown', '', None]:
                anomaly = create_anomaly(
                    action=action,
                    anomaly_type='unknown_vendor',
                    severity='low',
                    device_id=device_id,
                    device_data=device,
                    description=f"Устройство с неизвестным производителем: {device_id}"
                )
                anomalies_found.append(anomaly)
        
        # 4. Обнаружение подозрительной активности (слишком много устройств одного типа)
        vendor_counts = defaultdict(int)
        for device in current_devices:
            if isinstance(device, dict):
                vendor = device.get('vendor', 'Unknown')
                vendor_counts[vendor] += 1
        
        for vendor, count in vendor_counts.items():
            if count > 10 and vendor.lower() != 'unknown':
                sample_device = next(d for d in current_devices if d.get('vendor') == vendor)
                anomaly = create_anomaly(
                    action=action,
                    anomaly_type='suspicious_activity',
                    severity='high',
                    device_id=f"multiple_{vendor}",
                    device_data=sample_device,
                    description=f"Подозрительная активность: {count} устройств производителя {vendor}",
                    metadata={
                        'vendor': vendor,
                        'device_count': count,
                        'threshold': 10
                    }
                )
                anomalies_found.append(anomaly)
        
        if anomalies_found:
            logger.info(f"Обнаружено {len(anomalies_found)} аномалий в полигоне {action.polygon.name}")
        
        return len(anomalies_found)
        
    except PolygonAction.DoesNotExist:
        logger.error(f"Действие с ID {action_id} не найдено")
        return 0
    except Exception as e:
        logger.error(f"Ошибка при обнаружении аномалий: {e}")
        raise


def create_anomaly(action: PolygonAction, anomaly_type: str, severity: str, 
                  device_id: str, device_data: Dict[str, Any], description: str, 
                  metadata: Dict[str, Any] = None) -> AnomalyDetection:
    """
    Создает запись об аномалии
    """
    recent_anomaly = AnomalyDetection.objects.filter(
        polygon_action=action,
        anomaly_type=anomaly_type,
        device_id=device_id,
        detected_at__gte=timezone.now() - timezone.timedelta(hours=1)
    ).first()
    
    if recent_anomaly:
        logger.info(f"Аномалия {anomaly_type} для устройства {device_id} уже была обнаружена недавно")
        return recent_anomaly
    
    anomaly = AnomalyDetection.objects.create(
        polygon_action=action,
        anomaly_type=anomaly_type,
        severity=severity,
        device_id=device_id,
        device_data=device_data,
        description=description,
        metadata=metadata or {}
    )
    
    logger.info(f"Создана аномалия {anomaly_type} для устройства {device_id} в полигоне {action.polygon.name}")
    return anomaly


@shared_task
def retry_failed_notifications():
    """
    Повторно отправляет неудачные уведомления через WebSocket
    Используется системой для автоматической повторной отправки
    """
    from .notification_utils import retry_failed_notifications as retry_util
    
    retry_count, success_count = retry_util()
    logger.info(f"Повторно отправлено {retry_count} уведомлений, успешно: {success_count}")
    return {'retried': retry_count, 'successful': success_count}


