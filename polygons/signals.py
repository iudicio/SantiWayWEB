"""
Django сигналы для автоматической обработки аномалий и уведомлений
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import AnomalyDetection
from .notification_utils import create_and_send_notifications

logger = logging.getLogger(__name__)


@receiver(post_save, sender=AnomalyDetection)
def handle_new_anomaly(sender, instance, created, **kwargs):
    """
    Обработчик создания новой аномалии
    Автоматически создает и отправляет уведомления
    """
    if created:
        logger.info(f"New anomaly detected: {instance.id} - {instance.get_anomaly_type_display()}")
        
        try:
            notifications = create_and_send_notifications(instance)
            logger.info(f"Created {len(notifications)} notifications for anomaly {instance.id}")
        except Exception as e:
            logger.error(f"Error creating notifications for anomaly {instance.id}: {e}")

