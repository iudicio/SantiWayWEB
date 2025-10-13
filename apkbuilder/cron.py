from django.utils import timezone
import logging


log = logging.getLogger(__name__)


# TODO таска на удаление апк файлов через день
def delete_background_task():
    """
    Удаляет физические файлы, которым > 24 часов.
    Запускается каждые 5 минут через Celery Beat.
    """
    now = timezone.localtime()
    message = f"[cron] Тестовая задача: {now:%Y-%m-%d %H:%M:%S}"
    print(message)  # увидишь это в docker logs
    log.info(message)  # попадёт и в django-логгер (если настроен)

