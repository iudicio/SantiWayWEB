import os
from datetime import datetime, timezone
from typing import Dict, Any

from celery.utils.log import get_task_logger
from django.apps import apps
from django.db import transaction
from django.utils import timezone

from SantiWayWEB.celery_app import celery_app


log = get_task_logger(__name__)

android_url = os.getenv("ANDROID_REPO_URL", "")


TERMINAL_STATUSES = {"success", "failed"}


@celery_app.task(name='apkget', queue='apkget')
def apk_get_task(messages: Dict[str, Any]):
    APKBuild = apps.get_model('apkbuilder', 'APKBuild')

    status = messages.get("status")
    build_id = messages.get("apk_build_id")

    if not build_id:
        log.error("apkget: нет apk_build_id в message")
        return {"ok": False, "error": "missing apk_build_id"}

    log.info(f"Получен статус: {status}")

    try:
        with transaction.atomic():
            build = APKBuild.objects.select_for_update().get(id=build_id)

            update_fields = []

            if status and status != build.status:
                build.status = status
                update_fields.append("status")

            # если статус финальный — фиксируем время завершения (один раз)
            if status in TERMINAL_STATUSES and build.completed_at is None:
                build.completed_at = datetime.now(timezone.utc)
                update_fields.append("completed_at")

            if update_fields:
                build.save(update_fields=update_fields)

            log.info(f"apkget: обновлён build {build_id}: "
                     f"status={status}")
            return {"ok": True, "apk_build_id": build_id, "updated": update_fields}

    except APKBuild.DoesNotExist:
        log.error(f"apkget: APKBuild {build_id} не найден")
        return {"ok": False, "error": "not found", "apk_build_id": build_id}