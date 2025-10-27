import base64
import os
from datetime import datetime, timezone
from typing import Any, Dict

from django.apps import apps
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from celery import shared_task
from celery.utils.log import get_task_logger

from SantiWayWEB.celery_app import celery_app

log = get_task_logger(__name__)

android_url = os.getenv("ANDROID_REPO_URL", "")


TERMINAL_STATUSES = {"success", "failed"}


@celery_app.task(name="apkget", queue="apkget")
def apk_get_task(messages: Dict[str, Any]):
    APKBuild = apps.get_model("apkbuilder", "APKBuild")

    status = messages.get("status")
    build_id = messages.get("apk_build_id")

    if not build_id:
        log.error("apkget: нет apk_build_id в message")
        return {"ok": False, "error": "missing apk_build_id"}

    log.info(f"apkget: получен статус={status} для build_id={build_id}")

    try:
        with transaction.atomic():
            build = APKBuild.objects.select_for_update().get(id=build_id)

            update_fields = []

            if status == "success":
                b64 = messages.get("apk_base64")
                filename = messages.get("apk_filename") or "app.apk"
                content_type = (
                    messages.get("content_type")
                    or "application/vnd.android.package-archive"
                )

                if not b64:
                    log.error("apkget: status=success, но apk_base64 отсутствует")
                    # помечаем как failed, чтобы не зависло в ожидании файла
                    status = "failed"

                else:
                    try:
                        data = base64.b64decode(b64)
                        # сохраняем файл в FileField (upload_to='apks/')
                        build.apk_file.save(filename, ContentFile(data), save=False)
                        update_fields.append("apk_file")
                        log.info(
                            f"apkget: APK сохранён в build {build_id} как {filename} ({len(data)} байт)"
                        )
                    except Exception as e:
                        log.exception("apkget: ошибка сохранения APK")
                        status = "failed"

            if status and status != build.status:
                build.status = status
                update_fields.append("status")

            # если статус финальный — фиксируем время завершения (один раз)
            if status in TERMINAL_STATUSES and build.completed_at is None:
                build.completed_at = datetime.now(timezone.utc)
                update_fields.append("completed_at")

            if update_fields:
                build.save(update_fields=update_fields)

            log.info(
                f"apkget: обновлён build {build_id}: "
                f"status={build.status}, "
                f"updated={update_fields}"
            )
            return {"ok": True, "apk_build_id": build_id, "updated": update_fields}

    except APKBuild.DoesNotExist:
        log.error(f"apkget: APKBuild {build_id} не найден")
        return {"ok": False, "error": "not found", "apk_build_id": build_id}
