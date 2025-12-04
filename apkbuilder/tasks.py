import base64
import os
from datetime import datetime
from typing import Dict, Any

from celery import shared_task
from celery.utils.log import get_task_logger
from django.apps import apps
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone as dj_timezone

from SantiWayWEB.celery_app import celery_app
from notifications.services import send_notification_to_api_key

logger = get_task_logger(__name__)

android_url = os.getenv("ANDROID_REPO_URL", "")

TERMINAL_STATUSES = {"success", "failed"}
CHUNK_SIZE = 128 * 1024


@celery_app.task(name='apkget', queue='apkget')
def apk_get_task(messages: Dict[str, Any]):
    """
    Обработка входящего сообщения с APK:
    - сохраняет apk в APKBuild.apk_file
    - обновляет статус/completed_at
    - если success -> отправляет APK батчами по CHUNK_SIZE через send_notification_to_api_key
    """
    APKBuild = apps.get_model('apkbuilder', 'APKBuild')

    status = messages.get("status")
    build_id = messages.get("apk_build_id")

    if not build_id:
        logger.error("apkget: нет apk_build_id в message")
        return {"ok": False, "error": "missing apk_build_id"}

    logger.info(f"apkget: получен статус={status} для build_id={build_id}")

    try:
        with transaction.atomic():
            build = APKBuild.objects.select_for_update().get(id=build_id)

            update_fields = []

            if status == "success":
                b64 = messages.get("apk_base64")
                filename = messages.get("apk_filename") or "app.apk"
                content_type = messages.get("content_type") or "application/vnd.android.package-archive"

                if not b64:
                    logger.error("apkget: status=success, но apk_base64 отсутствует")
                    status = "failed"
                else:
                    try:
                        data_bytes = base64.b64decode(b64)
                        # сохраняем файл в FileField (upload_to='apks/')
                        build.apk_file.save(filename, ContentFile(data_bytes), save=False)
                        update_fields.append("apk_file")
                        logger.info(f"apkget: APK сохранён в build {build_id} как {filename} ({len(data_bytes)} байт)")
                    except Exception:
                        logger.exception("apkget: ошибка сохранения APK")
                        status = "failed"

            if status and status != build.status:
                build.status = status
                update_fields.append("status")

            if status in TERMINAL_STATUSES and build.completed_at is None:
                build.completed_at = dj_timezone.now()
                update_fields.append("completed_at")

            if update_fields:
                build.save(update_fields=update_fields)

            # Попытка отправить уведомление(я). Основная логика — отправка чанками если success
            api_key_obj = getattr(build, "api_key", None)
            if not api_key_obj:
                logger.warning("apkget: APKBuild %s не имеет api_key, уведомление не отправлено", build.id)
                return {"ok": True, "apk_build_id": build_id, "updated": update_fields}

            # Формируем title/text в зависимости от статуса
            if build.status == "success":
                title = f"Сборка {build.app_version or build.id} успешно завершена"
                text = f"APKBuild {build.id} собран успешно"
            else:
                title = f"Сборка {build.app_version or build.id} завершена с ошибкой"
                text = f"APKBuild {build.id} завершен со статусом: {build.status}"

            # Если success и есть файл — отправляем батчами
            if build.status == "success" and build.apk_file:
                try:
                    # Открываем файл в бинарном режиме (stream) — безопасно для больших файлов
                    with build.apk_file.open("rb") as f:
                        # Получим общий размер (если доступен)
                        try:
                            f.seek(0, os.SEEK_END)
                            total_size = f.tell()
                            f.seek(0)
                        except Exception:
                            total_size = None

                        if total_size:
                            chunk_count = (total_size + CHUNK_SIZE - 1) // CHUNK_SIZE
                        else:
                            # если размер неизвестен — будем считать до EOF и увеличивать chunk_count динамически
                            chunk_count = None

                        logger.info("apkget: start sending APK in chunks: build=%s filename=%s total_size=%s",
                                    build.id, os.path.basename(build.apk_file.name), total_size)

                        chunk_index = 0
                        sent_chunks = 0
                        # если заранее знаем chunk_count, используем; иначе будем вычислять и уведомлять клиент, что chunk_count may be None
                        while True:
                            chunk = f.read(CHUNK_SIZE)
                            if not chunk:
                                break

                            # Если chunk_count не вычислен заранее, попробуем посчитать на лету:
                            if chunk_count is None:
                                sent_chunks += 1
                                # Мы не знаем общее количество заранее — отправляем chunk_index и leave chunk_count=None.
                                current_chunk_count = None
                            else:
                                current_chunk_count = chunk_count

                            meta = {
                                "apk_chunk": True,
                                "chunk_index": chunk_index,
                                "chunk_count": current_chunk_count,
                                "filename": os.path.basename(build.apk_file.name),
                                "build_id": str(build.id),
                            }

                            # Попробуем вызвать send_notification_to_api_key с meta.
                            # Если он не поддерживает meta — в fallback встроим мета в текст.
                            try:
                                send_notification_to_api_key(
                                    str(api_key_obj.key),
                                    recorded_at=dj_timezone.now().isoformat(),
                                    title=f"{title} (chunk {chunk_index + 1}{'' if current_chunk_count is None else f'/{current_chunk_count}'})",
                                    text=text,
                                    notif_type="SYSTEM",
                                    coords=None,
                                    binary_contents=[chunk],  # bytes
                                    binary_types=[content_type],
                                    meta=meta,
                                )
                            except TypeError:
                                # fallback: send_notification_to_api_key не принимает meta — встраиваем мета в text
                                fallback_text = f"{text} [apk_chunk=1 chunk_index={chunk_index} chunk_count={current_chunk_count} build_id={build.id} filename={os.path.basename(build.apk_file.name)}]"
                                send_notification_to_api_key(
                                    str(api_key_obj.key),
                                    recorded_at=dj_timezone.now().isoformat(),
                                    title=f"{title} (chunk {chunk_index + 1}{'' if current_chunk_count is None else f'/{current_chunk_count}'})",
                                    text=fallback_text,
                                    notif_type="SYSTEM",
                                    coords=None,
                                    binary_contents=[chunk],
                                    binary_types=[content_type],
                                )
                            except Exception:
                                logger.exception("apkget: ошибка при отправке чанка index=%s for build=%s",
                                                 chunk_index, build.id)
                                # не ломаем цикл — пытаемся отправить следующие чанки

                            chunk_index += 1

                        # Если заранее знали chunk_count, можем отправить финальную метку; иначе отправить маркер завершения
                        final_meta = {
                            "apk_chunk_complete": True,
                            "build_id": str(build.id),
                            "filename": os.path.basename(build.apk_file.name),
                            "chunks_sent": chunk_index,
                        }
                        try:
                            send_notification_to_api_key(
                                str(api_key_obj.key),
                                recorded_at=dj_timezone.now().isoformat(),
                                title=f"{title} (APK transfer completed)",
                                text=f"APK transfer completed: {os.path.basename(build.apk_file.name)}, chunks={chunk_index}",
                                notif_type="SYSTEM",
                                coords=None,
                                binary_contents=None,
                                binary_types=None,
                                meta=final_meta,
                            )
                        except TypeError:
                            # fallback: embed final_meta into text
                            send_notification_to_api_key(
                                str(api_key_obj.key),
                                recorded_at=dj_timezone.now().isoformat(),
                                title=f"{title} (APK transfer completed)",
                                text=f"APK transfer completed: {os.path.basename(build.apk_file.name)}, chunks={chunk_index} build_id={build.id}",
                                notif_type="SYSTEM",
                                coords=None,
                                binary_contents=None,
                                binary_types=None,
                            )
                        except Exception:
                            logger.exception("apkget: ошибка при отправке финального уведомления для build=%s",
                                             build.id)

                        logger.info("apkget: finished sending APK chunks for build=%s total_chunks=%s", build.id,
                                    chunk_index)

                except Exception:
                    logger.exception("apkget: ошибка при чтении/отправке APK батчами для build=%s", build.id)
            else:
                # Если не success — просто отправим обычное уведомление (без бинарного содержимого)
                try:
                    send_notification_to_api_key(
                        str(api_key_obj.key),
                        recorded_at=dj_timezone.now().isoformat(),
                        title=title,
                        text=text,
                        notif_type="SYSTEM" if build.status == "success" else "ALARM",
                        coords=None,
                        binary_contents=None,
                        binary_types=None,
                    )
                    logger.info("apkget: отправлено простое уведомление для build=%s", build.id)
                except Exception:
                    logger.exception("apkget: не удалось отправить простое уведомление для build=%s", build.id)

    except APKBuild.DoesNotExist:
        logger.error("apkget: APKBuild %s не найден", build_id)
        return {"ok": False, "error": "not found", "apk_build_id": build_id}

    return {"ok": True, "apk_build_id": build_id, "updated": update_fields}