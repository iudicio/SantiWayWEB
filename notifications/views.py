from os import getenv
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import models
import json
import hmac
import hashlib
from celery import Celery
from django.conf import settings

from apkbuilder.models import APKBuild


logger = logging.getLogger(__name__)

# Инициализация Celery клиента (аналогично вашему подходу)
BROKER_URL = getenv('CELERY_BROKER_URL', 'amqp://celery:celerypassword@rabbitmq:5672/')
celery_client = Celery('apkbuild_producer', broker=BROKER_URL)


def handle_github_notification(payload):
    """Обрабатывает уведомления от GitHub"""
    repo_name = payload['repository']['full_name']
    branch = payload['ref'].split('/')[-1]

    logger.info(f"📢 УВЕДОМЛЕНИЕ ОБ ОБНОВЛЕНИИ:")
    logger.info(f"   📦 Репозиторий: {repo_name}")
    logger.info(f"   🌿 Ветка: {branch}")

    for i, commit in enumerate(payload['commits'], 1):
        logger.info(f"   📝 Коммит {i}: {commit['message']}")


def rebuild_single_apk(build, latest_commit):
    """Пересобирает одну APK запись"""
    # Обновляем статус и очищаем предыдущие данные
    build.status = "pending"
    build.app_version = latest_commit
    build.completed_at = None

    # Удаляем старый APK файл если он существует
    if build.apk_file:
        build.apk_file.delete(save=False)

    build.save()

    # Отправляем задачу в Celery
    try:
        celery_client.send_task(
            'apkbuild',
            args=[{
                "key": str(build.api_key.key),
                "apk_build_id": str(build.id)
            }],
            queue='apkbuilder'
        )
        logger.info(f"✅ Задача отправлена в очередь для ключа: {build.api_key.key}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки задачи: {e}")
        build.status = "failed"
        build.save()
        return False


def trigger_apk_rebuild(payload):
    """Запускает пересборку APK для всех записей с устаревшей версией"""
    latest_commit = payload['after']  # Хэш последнего коммита

    logger.info(f"🚀 ЗАПУСК ПЕРЕСБОРКИ APK ДЛЯ КОММИТА: {latest_commit}")

    # Находим все записи APKBuild, которые нужно пересобрать
    builds_to_rebuild = APKBuild.objects.filter(
        models.Q(app_version__isnull=True) |
        ~models.Q(app_version=latest_commit)
    ).exclude(
        status__in=['building', 'pending']
    )

    logger.info(f"📊 Найдено записей для пересборки: {builds_to_rebuild.count()}")

    rebuilt_count = 0
    rebuilt_ids = []

    for build in builds_to_rebuild:
        try:
            if rebuild_single_apk(build, latest_commit):
                rebuilt_count += 1
                rebuilt_ids.append(str(build.id))
        except Exception as e:
            logger.error(f"❌ Ошибка пересборки для APKBuild {build.id}: {e}")


@csrf_exempt #убрана проверка CSRF для вебхуков, т.к. там проверяется по подписи secret
@require_POST
def github_webhook(request):
    """Обработчик вебхуков от GitHub для уведомлений"""
    try:
        if hasattr(settings, 'GITHUB_WEBHOOK_SECRET') and settings.GITHUB_WEBHOOK_SECRET:
            signature = request.headers.get('X-Hub-Signature-256', '')
            body = request.body

            expected_signature = 'sha256=' + hmac.new(
                settings.GITHUB_WEBHOOK_SECRET.encode(),
                body,
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_signature):
                return JsonResponse({'error': 'Invalid signature'}, status=401)

        # Парсим JSON
        payload = json.loads(request.body)

        # Проверяем, что это push в main ветку
        if (payload.get('ref') == 'refs/heads/main' and
                request.headers.get('X-GitHub-Event') == 'push'):
            logger.info("🔔 УВЕДОМЛЕНИЕ: Обнаружен PUSH в main")

            # Запускаем функцию уведомления
            handle_github_notification(payload)

            # Запускаем пересборку APK
            trigger_apk_rebuild(payload)

            return JsonResponse({'status': 'success'}, status=200)

        return JsonResponse({'status': 'ignored'}, status=200)

    except Exception as e:
        logger.error(f"❌ Ошибка обработки вебхука: {e}")
        return JsonResponse({'error': str(e)}, status=500)