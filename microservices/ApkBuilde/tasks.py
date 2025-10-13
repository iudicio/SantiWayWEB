import base64
import os
import threading
from typing import Dict, Any
from celery import Celery
from celery_app import app
from celery.utils.log import get_task_logger
from build_apk import clone_public_repo, should_clone_repository, process_apk_build


log = get_task_logger(__name__)

android_url = os.getenv("ANDROID_REPO_URL", "")

BROKER_URL = os.getenv(
    "CELERY_BROKER_URL", "amqp://celery:celerypassword@rabbitmq:5672/"
)
celery_client = Celery("apkget_producer", broker=BROKER_URL)

# Глобальная блокировка для клонирования
clone_lock = threading.Lock()
is_cloning = False


def send_to_queue(task_name: str, message: Dict[str, Any], queue_name: str):
    """Отправка сообщения в очередь RabbitMQ"""
    celery_client.send_task(task_name, args=[message], queue=queue_name)


@app.task(name="apkbuild", queue="apkbuilder")
def apk_build_task(messages: Dict[str, Any]):
    global is_cloning

    api_key = messages.get("key")
    apk_build_id = messages.get("apk_build_id")
    status = "success"

    if api_key:
        try:
            log.info(f"Api-key: {api_key} поступил в работу")
        except Exception:
            log.error("Ошибка получения Api-key")

    target_dir = "./android_repo"

    # Проверяем нужно ли клонировать репозиторий
    if should_clone_repository(android_url, target_dir):
        # Если идет клонирование, ждем
        if is_cloning:
            log.info("Идет клонирование репозитория, ожидание...")
            import time

            time.sleep(5)
            # Перезапускаем задачу через несколько секунд
            apk_build_task.apply_async(args=[messages], countdown=10)
            return "Waiting for repository clone..."

        # Захватываем блокировку для клонирования
        with clone_lock:
            is_cloning = True
            try:
                log.info("Начинаем клонирование/обновление репозитория...")
                clone = clone_public_repo(android_url, target_dir)

                if clone:
                    log.info("Репозиторий успешно клонирован/обновлен.")
                else:
                    status = "failed"
                    log.error("Ошибка при клонировании репозитория.")
                    send_to_queue(
                        "apkget",
                        {"status": status, "apk_build_id": apk_build_id},
                        "apkget",
                    )
                    return "ERROR"
            finally:
                is_cloning = False

    try:
        # Теперь функция возвращает путь к итоговому APK
        final_apk_path = process_apk_build(api_key, target_dir, android_url)
        # Собираем бинарник в base64
        with open(final_apk_path, "rb") as f:
            apk_bytes_b64 = base64.b64encode(f.read()).decode("ascii")

        apk_filename = os.path.basename(final_apk_path)
        apk_size = os.path.getsize(final_apk_path)
        content_type = "application/vnd.android.package-archive"

        payload = {
            "status": status,
            "apk_build_id": apk_build_id,
            "apk_filename": apk_filename,
            "apk_size": apk_size,
            "content_type": content_type,
            "apk_base64": apk_bytes_b64,
        }

        send_to_queue("apkget", payload, "apkget")
        return status

    except Exception as e:
        log.exception("Сборка/отправка APK завершилась ошибкой")
        status = "failed"
        send_to_queue(
            "apkget",
            {"status": status, "apk_build_id": apk_build_id, "error": str(e)},
            "apkget",
        )
        return "ERROR"
