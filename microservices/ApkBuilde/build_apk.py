import os
import shutil
import subprocess
from celery.utils.log import get_task_logger


log = get_task_logger(__name__)


def process_apk_build(key: str, target_dir: str, android_url: str) -> str:
    """Основная логика сборки APK"""
    api_key = key

    # Перед каждой сборкой проверяем актуальность репозитория
    if should_clone_repository(android_url, target_dir):
        log.warning("Репозиторий устарел во время обработки, требуется пересборка")
        # Можно либо перезапустить задачу, либо продолжить со старым репо
        # В зависимости от требований к актуальности

    log.info(f"Обрабатываем сборку APK для ключа: {api_key}")

    # TODO: Добавить логику сборки APK
    # 1. Обновление API ключа в репозитории
    # 2. Сборка APK
    # 3. Возврат результата

    return f"APK build completed for key: {api_key}"


def clone_public_repo(repo_url, target_dir):
    """Простая функция для быстрого клонирования"""
    if os.path.exists(target_dir):
        try:
            # Вместо удаления, пытаемся обновить через pull
            log.info(f"Пытаемся обновить существующий репозиторий в {target_dir}")

            # Сбрасываем все локальные изменения
            subprocess.run(['git', 'reset', '--hard'], cwd=target_dir, check=True)
            # Получаем последние изменения
            subprocess.run(['git', 'pull', 'origin', 'main'], cwd=target_dir, check=True)

            log.info("Репозиторий успешно обновлен через git pull")
            return True
        except subprocess.CalledProcessError:
            log.warning("Не удалось обновить через git pull, удаляем и клонируем заново")
            shutil.rmtree(target_dir)
    try:
        log.info(f"Клонирование репозитория {repo_url} в {target_dir}")
        result = subprocess.run(
            ['git', 'clone', repo_url, target_dir],
            check=True,
            capture_output=True,
            text=True
        )
        log.info("Репозиторий успешно клонирован.")
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"Ошибка при клонировании: {e.stderr}")
        return False
    except Exception as e:
        log.error(f"Неожиданная ошибка при клонировании: {e}")
        return False


def should_clone_repository(repo_url, target_dir):
    """
    Проверяет, нужно ли клонировать репозиторий.
    Возвращает True если:
    1. Папка не существует
    2. Папка пустая
    3. Существующий репозиторий имеет другой origin URL
    """
    # Если папка не существует
    if not os.path.exists(target_dir):
        log.info(f"Папка {target_dir} не существует, требуется клонирование.")
        return True

    # Если папка существует, но пустая
    if not os.listdir(target_dir):
        log.info(f"Папка {target_dir} пустая, требуется клонирование.")
        return True

    # Проверяем, является ли папка git репозиторием
    git_dir = os.path.join(target_dir, '.git')
    if not os.path.exists(git_dir):
        log.info(f"Папка {target_dir} не является git репозиторием, требуется клонирование.")
        return True

    try:
        # Получаем текущий origin URL репозитория
        result = subprocess.run(
            ['git', 'config', '--get', 'remote.origin.url'],
            cwd=target_dir,
            capture_output=True,
            text=True,
            check=True
        )
        current_url = result.stdout.strip()

        # Сравниваем URL (учитываем возможные варианты записи одного и того же URL)
        def normalize_url(url):
            """Нормализует URL для сравнения"""
            url = url.lower().strip()
            # Убираем .git в конце если есть
            if url.endswith('.git'):
                url = url[:-4]
            # Заменяем разные формы записи
            url = url.replace('https://', '').replace('http://', '').replace('git@', '')
            url = url.replace('github.com/', 'github.com:')
            return url

        if normalize_url(current_url) != normalize_url(repo_url):
            log.info(f"Текущий репозиторий отличается от целевого: {current_url} vs {repo_url}")
            return True
        try:
            # Получаем последний коммит из удаленного репозитория
            subprocess.run(['git', 'fetch', 'origin'], cwd=target_dir,
                           capture_output=True, check=True)

            # Сравниваем локальный и удаленный коммит
            local_commit = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=True
            ).stdout.strip()

            remote_commit = subprocess.run(
                ['git', 'rev-parse', 'origin/main'],  # или origin/master
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=True
            ).stdout.strip()

            if local_commit != remote_commit:
                log.info(f"Репозиторий устарел: локальный {local_commit[:8]} != удаленный {remote_commit[:8]}")
                return True
            else:
                log.info("Репозиторий актуален")
                return False

        except subprocess.CalledProcessError as e:
            log.warning(f"Не удалось проверить актуальность репозитория: {e}")
            # Если не удалось проверить актуальность, считаем что нужно обновить
            return True

    except subprocess.CalledProcessError:
        log.warning("Не удалось получить информацию о remote origin")
        return True
    except Exception as e:
        log.error(f"Ошибка при проверке репозитория: {e}")
        return True