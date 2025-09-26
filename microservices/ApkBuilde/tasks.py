import os
import threading
from typing import Dict, Any
from celery_app import app
from celery.utils.log import get_task_logger
from build_apk import clone_public_repo, should_clone_repository, process_apk_build

log = get_task_logger(__name__)

android_url = os.getenv("ANDROID_REPO_URL", "")
# Глобальная блокировка для клонирования
clone_lock = threading.Lock()
is_cloning = False


@app.task(name='apkbuild', queue='apkbuilder')
def apk_build_task(messages: Dict[str, Any]):
    global is_cloning

    api_key = messages.get("key")
    status = "Ready"

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
                    status = "Ready"
                else:
                    status = "Error"
                    log.error("Ошибка при клонировании репозитория.")
                    # TODO Отправка статуса в БД
                    return

            finally:
                is_cloning = False
    else:
        log.info("Репозиторий уже актуален, клонирование не требуется.")

    # process_apk_build(api_key, target_dir, android_url)
    log.info(f"status: {status}")