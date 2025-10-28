"""
Утилиты для работы с уведомлениями об аномалиях
"""
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone

logger = logging.getLogger(__name__)


def send_notification_via_websocket(notification):
    """
    Отправить уведомление через WebSocket
    
    Args:
        notification: объект Notification
    """
    channel_layer = get_channel_layer()
    
    if not channel_layer:
        logger.error("Channel layer not configured")
        return False
    
    try:
        user = notification.anomaly.polygon_action.polygon.user
        user_group_name = f"user_notifications_{user.id}"
        
        notification_data = {
            'id': str(notification.id),
            'title': notification.title,
            'message': notification.message,
            'severity': notification.anomaly.severity,
            'anomaly_type': notification.anomaly.anomaly_type,
            'anomaly_id': str(notification.anomaly.id),
            'polygon_id': str(notification.anomaly.polygon_action.polygon.id),
            'polygon_name': notification.anomaly.polygon_action.polygon.name,
            'device_id': notification.anomaly.device_id,
            'device_data': notification.anomaly.device_data,
            'created_at': notification.created_at.isoformat(),
            'detected_at': notification.anomaly.detected_at.isoformat(),
        }
        
        async_to_sync(channel_layer.group_send)(
            user_group_name,
            {
                'type': 'notification.alert',
                'notification': notification_data
            }
        )
        
        notification.mark_as_sent()
        
        logger.info(f"Notification {notification.id} sent via WebSocket to user {user.username}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending notification via WebSocket: {e}")
        notification.mark_as_failed()
        return False


def create_and_send_notifications(anomaly):
    """
    Создать и отправить уведомления для всех целей (targets) аномалии
    
    Args:
        anomaly: объект AnomalyDetection
    """
    from .models import Notification
    
    notification_targets = anomaly.polygon_action.notification_targets.filter(
        is_active=True
    )
    
    if not notification_targets.exists():
        logger.warning(f"No notification targets for anomaly {anomaly.id}")
        return []
    
    created_notifications = []
    
    for target in notification_targets:
        title = f"🚨 {anomaly.get_anomaly_type_display()}"
        message = (
            f"Обнаружена аномалия в полигоне '{anomaly.polygon_action.polygon.name}'\n"
            f"Тип: {anomaly.get_anomaly_type_display()}\n"
            f"Уровень: {anomaly.get_severity_display()}\n"
            f"Устройство: {anomaly.device_id}\n"
            f"Описание: {anomaly.description}"
        )
        
        notification = Notification.objects.create(
            anomaly=anomaly,
            target=target,
            title=title,
            message=message,
            status='pending'
        )
        
        if target.target_type in ['api_key', 'device']:
            send_notification_via_websocket(notification)
        else:
            logger.info(f"Skipping notification for deprecated target type: {target.target_type}")
            notification.mark_as_failed()
        
        created_notifications.append(notification)
    
    return created_notifications


def retry_failed_notifications():
    """
    Повторная отправка неудачных уведомлений
    Может быть вызвана из Celery task по расписанию
    """
    from .models import Notification
    
    failed_notifications = Notification.objects.filter(
        status='failed'
    ).select_related(
        'anomaly__polygon_action__polygon',
        'target'
    )
    
    retry_count = 0
    success_count = 0
    
    for notification in failed_notifications:
        if notification.can_retry():
            if send_notification_via_websocket(notification):
                success_count += 1
            retry_count += 1
    
    logger.info(f"Retried {retry_count} failed notifications, {success_count} successful")
    return retry_count, success_count


def get_unread_count(user):
    """
    Получить количество непрочитанных уведомлений для пользователя
    
    Args:
        user: объект User
    
    Returns:
        int: количество непрочитанных уведомлений
    """
    from .models import Notification
    
    return Notification.objects.filter(
        anomaly__polygon_action__polygon__user=user,
        status__in=['pending', 'sent', 'delivered']
    ).count()


def mark_all_as_read(user):
    """
    Отметить все уведомления пользователя как прочитанные
    
    Args:
        user: объект User
    
    Returns:
        int: количество обновленных уведомлений
    """
    from .models import Notification
    
    count = Notification.objects.filter(
        anomaly__polygon_action__polygon__user=user,
        status__in=['pending', 'sent', 'delivered']
    ).update(
        status='read',
        read_at=timezone.now()
    )
    
    return count

