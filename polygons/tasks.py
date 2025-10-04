"""
Celery задачи для работы с полигонами
"""
from celery import shared_task
from django.utils import timezone
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
            action_type='mac_monitoring',
            defaults={
                'parameters': {
                    'monitoring_interval': monitoring_interval,
                    'user_api_key': user_api_key
                },
                'status': 'running',
                'task_id': self.request.id,
                'started_at': timezone.now()
            }
        )

        if not created:
            action.task_id = self.request.id
            if action.status != 'running':
                logger.info(f"Действие {action.id} не активно ({action.status}), пропускаем тик")
                return
            action.save()

        devices = search_devices_in_polygon(
            polygon.geometry,
            user_api_key=user_api_key
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

        logger.info(f"Полигон {polygon.name}: найдено {len(mac_addresses)} MAC, перепланируем через {monitoring_interval}s")

        action_refreshed = PolygonAction.objects.filter(id=action.id).only('status').first()
        if action_refreshed and action_refreshed.status == 'running':
            monitor_mac_addresses.apply_async(
                args=[str(polygon.id), user_api_key, monitoring_interval],
                countdown=int(monitoring_interval)
            )
        else:
            logger.info(f"Действие {action.id} остановлено со статусом {action_refreshed.status if action_refreshed else 'unknown'}")

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
            polygon_id=polygon_id,
            action_type='mac_monitoring',
            status='running'
        )
        from celery import current_app
        for action in actions:
            if action.task_id:
                current_app.control.revoke(action.task_id, terminate=True)
            action.status = 'stopped'
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
            polygon_id=polygon_id,
            status__in=['running', 'pending', 'paused']
        )
        from celery import current_app
        for action in qs:
            if action.task_id:
                current_app.control.revoke(action.task_id, terminate=True)
            action.status = 'stopped'
            action.completed_at = timezone.now()
            action.save()
            logger.info(f"Остановлено действие {action.action_type} для полигона {action.polygon_id}")
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
            for anomaly in anomalies_found:
                send_anomaly_notifications.delay(str(anomaly.id))
            
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
def send_anomaly_notifications(anomaly_id: str):
    """
    Отправляет уведомления о найденной аномалии всем целям
    """
    try:
        anomaly = AnomalyDetection.objects.get(id=anomaly_id)
        targets = NotificationTarget.objects.filter(
            polygon_action=anomaly.polygon_action,
            is_active=True
        )
        
        if not targets.exists():
            logger.info(f"Нет активных целей для уведомлений в действии {anomaly.polygon_action.id}")
            return 0
        
        notifications_created = 0
        
        for target in targets:
            title = f"🚨 Аномалия в полигоне {anomaly.polygon_action.polygon.name}"
            message = f"{anomaly.get_anomaly_type_display()}: {anomaly.description}"
            
            notification = Notification.objects.create(
                anomaly=anomaly,
                target=target,
                title=title,
                message=message,
                delivery_metadata={
                    'polygon_name': anomaly.polygon_action.polygon.name,
                    'severity': anomaly.severity,
                    'device_id': anomaly.device_id
                }
            )
            
            if target.target_type == 'api_key':
                send_api_notification.delay(str(notification.id))
            elif target.target_type == 'email':
                send_email_notification.delay(str(notification.id))
            elif target.target_type == 'webhook':
                send_webhook_notification.delay(str(notification.id))
            elif target.target_type == 'device':
                send_device_notification.delay(str(notification.id))
            
            notifications_created += 1
        
        logger.info(f"Создано {notifications_created} уведомлений для аномалии {anomaly_id}")
        return notifications_created
        
    except AnomalyDetection.DoesNotExist:
        logger.error(f"Аномалия с ID {anomaly_id} не найдена")
        return 0
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомлений: {e}")
        raise


@shared_task
def send_api_notification(notification_id: str):
    """
    Отправляет уведомление через API (сохраняет в базе для получения через API)
    """
    try:
        notification = Notification.objects.get(id=notification_id)
        
        # GET /api/notifications/
        notification.mark_as_sent()
        
        logger.info(f"API уведомление {notification_id} помечено как отправленное")
        return True
        
    except Notification.DoesNotExist:
        logger.error(f"Уведомление с ID {notification_id} не найдено")
        return False
    except Exception as e:
        logger.error(f"Ошибка при отправке API уведомления: {e}")
        notification = Notification.objects.get(id=notification_id)
        notification.mark_as_failed()
        raise


@shared_task
def send_email_notification(notification_id: str):
    """
    Отправляет email уведомление
    """
    try:
        notification = Notification.objects.get(id=notification_id)
        
        # TODO: Реализовать отправку email через Django mail или внешний сервис
        # Пока что просто помечаем как отправленное
        
        logger.info(f"Email уведомление отправлено на {notification.target.target_value}")
        notification.mark_as_sent()
        return True
        
    except Notification.DoesNotExist:
        logger.error(f"Уведомление с ID {notification_id} не найдено")
        return False
    except Exception as e:
        logger.error(f"Ошибка при отправке email: {e}")
        notification = Notification.objects.get(id=notification_id)
        notification.mark_as_failed()
        return False


@shared_task
def send_webhook_notification(notification_id: str):
    """
    Отправляет webhook уведомление
    """
    try:
        notification = Notification.objects.get(id=notification_id)
        
        import requests
        
        payload = {
            'notification_id': str(notification.id),
            'anomaly_id': str(notification.anomaly.id),
            'title': notification.title,
            'message': notification.message,
            'severity': notification.anomaly.severity,
            'polygon_name': notification.anomaly.polygon_action.polygon.name,
            'device_id': notification.anomaly.device_id,
            'detected_at': notification.anomaly.detected_at.isoformat(),
            'metadata': notification.delivery_metadata
        }
        
        response = requests.post(
            notification.target.target_value,
            json=payload,
            timeout=30,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            notification.mark_as_delivered()
            logger.info(f"Webhook уведомление успешно отправлено на {notification.target.target_value}")
            return True
        else:
            logger.error(f"Webhook вернул код {response.status_code}: {response.text}")
            notification.mark_as_failed()
            return False
            
    except Notification.DoesNotExist:
        logger.error(f"Уведомление с ID {notification_id} не найдено")
        return False
    except Exception as e:
        logger.error(f"Ошибка при отправке webhook: {e}")
        try:
            notification = Notification.objects.get(id=notification_id)
            notification.mark_as_failed()
        except:
            pass
        return False


@shared_task
def send_device_notification(notification_id: str):
    """
    Отправляет push-уведомление на устройство
    """
    try:
        notification = Notification.objects.get(id=notification_id)
        
        # TODO: Реализовать отправку push-уведомлений через FCM или другой сервис
        # Пока что просто помечаем как отправленное
        
        logger.info(f"Push уведомление отправлено на устройство {notification.target.target_value}")
        notification.mark_as_sent()
        return True
        
    except Notification.DoesNotExist:
        logger.error(f"Уведомление с ID {notification_id} не найдено")
        return False
    except Exception as e:
        logger.error(f"Ошибка при отправке push уведомления: {e}")
        notification = Notification.objects.get(id=notification_id)
        notification.mark_as_failed()
        return False


@shared_task
def retry_failed_notifications():
    """
    Повторно отправляет неудачные уведомления
    """
    failed_notifications = Notification.objects.filter(
        status='failed'
    ).select_related('target', 'anomaly')
    
    retried_count = 0
    
    for notification in failed_notifications:
        if notification.can_retry():
            if notification.target.target_type == 'api_key':
                send_api_notification.delay(str(notification.id))
            elif notification.target.target_type == 'email':
                send_email_notification.delay(str(notification.id))
            elif notification.target.target_type == 'webhook':
                send_webhook_notification.delay(str(notification.id))
            elif notification.target.target_type == 'device':
                send_device_notification.delay(str(notification.id))
            
            retried_count += 1
    
    logger.info(f"Повторно отправлено {retried_count} уведомлений")
    return retried_count


