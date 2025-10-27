import os
import shutil
import stat
import subprocess
from pathlib import Path

from celery.utils.log import get_task_logger
from defusedxml import ElementTree as ET

log = get_task_logger(__name__)


def cleanup_values_dir(values_dir: Path) -> None:
    """Удаляет из res/values всё, что не .xml (например .bak)."""
    if not values_dir.exists():
        return
    for p in values_dir.iterdir():
        if p.is_file() and p.suffix.lower() != ".xml":
            try:
                p.unlink()
            except Exception:
                pass


def inject_api_key_into_strings(repo_dir: Path, key: str) -> Path:
    """
    Гарантирует наличие <string name="api_key">KEY</string> в
    SantiWayANDROID/app/src/main/res/values/strings.xml (или string.xml).

    Возвращает путь к файлу strings.xml, в который был вшит ключ.
    """
    if not key:
        raise ValueError("API key пустой — нечего вшивать")

    # корень андроид-проекта — репозиторий SantiWayANDROID
    values_dir = repo_dir / "app" / "src" / "main" / "res" / "values"
    values_dir.mkdir(parents=True, exist_ok=True)

    # возможные имена файла
    strings_xml = values_dir / "strings.xml"
    alt_xml = values_dir / "string.xml"
    target = (
        strings_xml
        if strings_xml.exists()
        else (alt_xml if alt_xml.exists() else strings_xml)
    )

    if not target.exists():
        # создаём минимальный шаблон
        log.info("[api_key] strings.xml отсутствует — создаём новый")
        root = ET.Element("resources")
    else:
        try:
            root = ET.parse(target).getroot()
            if root.tag != "resources":
                raise ET.ParseError("Корневой тег не <resources>")
        except Exception as e:
            # если файл битый — переименуем в .bak и начнём с чистого
            log.warning(
                "[api_key] Не удалось распарсить %s (%s). Переименовываю в .bak и пересоздаю.",
                target,
                e,
            )
            shutil.move(str(target), str(target.with_suffix(target.suffix + ".bak")))
            root = ET.Element("resources")

    # ищем/создаём элемент <string name="api_key">
    api_el = None
    for child in list(root):
        if child.tag == "string" and child.attrib.get("name") == "api_key":
            api_el = child
            break
    if api_el is None:
        api_el = ET.SubElement(root, "string", {"name": "api_key"})

    # ставим текст ключа
    api_el.text = key

    # делаем бэкап перед записью, если есть старый файл
    if target.exists():
        backup = target.with_suffix(target.suffix + ".bak")
        try:
            shutil.copy2(target, backup)
        except Exception:
            pass

    # сохраняем с декларацией XML и utf-8
    tree = ET.ElementTree(root)
    # prettify простым переводом строк (ElementTree сам не форматирует)
    xml_bytes = ET.tostring(root, encoding="utf-8")
    xml_text = b'<?xml version="1.0" encoding="utf-8"?>\n' + xml_bytes

    with open(target, "wb") as f:
        f.write(xml_text)

    log.info("[api_key] API key вшит в %s", target)
    return target


def run_cmd(cmd, cwd=None, env=None, log_prefix=""):
    log.info("%s$ %s", log_prefix, " ".join(cmd))
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True)
    if proc.returncode != 0:
        log.error("%sSTDOUT:\n%s", log_prefix, proc.stdout)
        log.error("%sSTDERR:\n%s", log_prefix, proc.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    if proc.stdout:
        log.info("%s%s", log_prefix, proc.stdout)
    if proc.stderr:
        log.info("%s%s", log_prefix, proc.stderr)
    return proc


def have_keystore_env():
    return all(
        os.getenv(k)
        for k in ("KEYSTORE_PATH", "KEYSTORE_PASSWORD", "KEY_ALIAS", "KEY_PASSWORD")
    )


def find_apk(app_dir: Path, variant: str) -> Path:
    # Ищем стандартные артефакты Gradle
    # release: app-release.apk / app-release-unsigned.apk
    # debug:   app-debug.apk
    out = app_dir / "build" / "outputs" / "apk" / variant
    candidates = sorted(
        out.glob("*.apk"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not candidates:
        raise FileNotFoundError(f"APK не найден в {out}")
    return candidates[0]


def sign_with_apksigner(apk_path: Path) -> Path:
    """
    Подпись APK через apksigner из ANDROID_SDK_ROOT/build-tools/<ver>/apksigner
    Требуются переменные окружения:
      ANDROID_SDK_ROOT, KEYSTORE_PATH, KEYSTORE_PASSWORD, KEY_ALIAS, KEY_PASSWORD
    """
    sdk = os.getenv("ANDROID_SDK_ROOT") or os.getenv("ANDROID_HOME")
    if not sdk:
        raise RuntimeError("ANDROID_SDK_ROOT/ANDROID_HOME не задан")

    # выбираем самую новую версию build-tools, где есть apksigner
    build_tools_dir = Path(sdk) / "build-tools"
    bt_versions = [
        p
        for p in build_tools_dir.iterdir()
        if (p / "apksigner").exists() or (p / "apksigner.bat").exists()
    ]
    if not bt_versions:
        raise RuntimeError("apksigner не найден в build-tools")
    bt = sorted(bt_versions, key=lambda p: p.name)[-1]

    apksigner = str((bt / "apksigner").with_suffix(".bat" if os.name == "nt" else ""))
    ks = os.getenv("KEYSTORE_PATH")
    ks_pass = os.getenv("KEYSTORE_PASSWORD")
    alias = os.getenv("KEY_ALIAS")
    key_pass = os.getenv("KEY_PASSWORD")

    # (опционально) zipalign — современные пайплайны зачастую уже выровнены, пропустим для краткости

    # подписываем на месте -> итоговый файл получит суффикс -signed.apk
    signed_apk = apk_path.with_name(apk_path.stem + "-signed.apk")
    shutil.copy2(apk_path, signed_apk)

    cmd = [
        apksigner,
        "sign",
        "--ks",
        ks,
        "--ks-pass",
        f"pass:{ks_pass}",
        "--key-pass",
        f"pass:{key_pass}",
        "--ks-key-alias",
        alias,
        str(signed_apk),
    ]
    run_cmd(cmd, log_prefix="[apksigner] ")
    # проверка подписи
    run_cmd(
        [apksigner, "verify", "--print-certs", str(signed_apk)],
        log_prefix="[apksigner] ",
    )
    return signed_apk


def process_apk_build(key: str, target_dir: str, android_url: str) -> str:
    """
    1) Подготавливаем окружение (права на gradlew, JAVA_HOME/JDK)
    2) Собираем release, если есть keystore; иначе debug
    3) Если release собрался неудалённо (unsigned) — подписываем apksigner'ом
    4) Возвращаем путь к итоговому APK
    """
    repo_dir = Path(target_dir).resolve()
    app_dir = repo_dir / "app"

    # Вшиваем API_KEY до сборки
    if key:
        try:
            inject_api_key_into_strings(repo_dir, key)
        except Exception as e:
            # не падаем, а логируем — сборка всё равно может пройти, если проект ждёт -PapiKey
            log.warning("[api_key] Не удалось вшить ключ: %s", e)

    # На всякий случай ещё раз подметём мусор перед запуском Gradle
    cleanup_values_dir(repo_dir / "app" / "src" / "main" / "res" / "values")

    # gradlew исполняемый
    gradlew = repo_dir / ("gradlew.bat" if os.name == "nt" else "gradlew")
    if not gradlew.exists():
        raise FileNotFoundError("gradlew не найден в корне репозитория")
    try:
        if os.name != "nt":  # на Windows chmod смысла не имеет
            os.chmod(gradlew, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)  # 0o700
    # !!!Изменила, так как ругался CI. Если ApkBuilde не работает, скорее всего, причина в этом.
    # try:
    #     os.chmod(gradlew, 0o755)
    except Exception:
        pass

    env = os.environ.copy()

    env.setdefault("HOME", "/home/celery")
    env.setdefault("ANDROID_USER_HOME", "/home/celery/.android")
    env.setdefault("GRADLE_USER_HOME", str(Path(target_dir) / ".gradle"))

    # ВАЖНО: убрать возможный ANDROID_PREFS_ROOT, если пришёл из контейнера
    env.pop("ANDROID_PREFS_ROOT", None)

    if key:
        env["API_KEY"] = key

    # базовые флаги gradle для CI
    base = [str(gradlew), "--no-daemon", "--stacktrace", "--console=plain"]

    # Быстрый прогрев: ./gradlew help (не обязательно)
    try:
        run_cmd(base + ["help"], cwd=str(repo_dir), env=env, log_prefix="[gradle] ")
    except Exception:
        # не критично
        pass

    # Выбор варианта: если есть keystore — собираем release; иначе debug
    aim_release = have_keystore_env()

    # Сначала clean, потом сборка
    tasks = [":app:clean"]
    if aim_release:
        # попытка собрать релиз
        tasks += [":app:assembleRelease", f"-PapiKey={key}" if key else ""]
    else:
        # отладочный APK всегда подпишется debug-сертификатом автоматически
        tasks += [":app:assembleDebug", f"-PapiKey={key}" if key else ""]

    tasks = [t for t in tasks if t]  # убираем пустые

    run_cmd(base + tasks, cwd=str(repo_dir), env=env, log_prefix="[gradle] ")

    # Находим артефакт
    variant = "release" if aim_release else "debug"
    apk = find_apk(app_dir, variant)

    # Если релиз и файл неподписанный — подпишем
    final_apk = apk
    if aim_release and (
        "unsigned" in apk.name.lower() or "-unsigned" in apk.name.lower()
    ):
        final_apk = sign_with_apksigner(apk)

    # Сохраним/скопируем в понятное место (например ./artifacts/)
    artifacts = repo_dir / "artifacts"
    artifacts.mkdir(exist_ok=True)

    safe_key = (key or "no-key").replace("/", "_").replace("\\", "_")
    dst = artifacts / f"{safe_key}.apk"

    shutil.copy2(final_apk, dst)

    msg = f"APK готов: {dst}"
    log.info(msg)
    return str(dst)


def clone_public_repo(repo_url, target_dir):
    """Простая функция для быстрого клонирования"""
    if os.path.exists(target_dir):
        try:
            # Вместо удаления, пытаемся обновить через pull
            log.info(f"Пытаемся обновить существующий репозиторий в {target_dir}")

            # Сбрасываем все локальные изменения
            subprocess.run(["git", "reset", "--hard"], cwd=target_dir, check=True)
            # Получаем последние изменения
            subprocess.run(
                ["git", "pull", "origin", "main"], cwd=target_dir, check=True
            )

            log.info("Репозиторий успешно обновлен через git pull")
            return True
        except subprocess.CalledProcessError:
            log.warning(
                "Не удалось обновить через git pull, удаляем и клонируем заново"
            )
            shutil.rmtree(target_dir)
    try:
        log.info(f"Клонирование репозитория {repo_url} в {target_dir}")
        result = subprocess.run(
            ["git", "clone", repo_url, target_dir],
            check=True,
            capture_output=True,
            text=True,
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
    git_dir = os.path.join(target_dir, ".git")
    if not os.path.exists(git_dir):
        log.info(
            f"Папка {target_dir} не является git репозиторием, требуется клонирование."
        )
        return True

    try:
        # Получаем текущий origin URL репозитория
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=target_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        current_url = result.stdout.strip()

        # Сравниваем URL (учитываем возможные варианты записи одного и того же URL)
        def normalize_url(url):
            """Нормализует URL для сравнения"""
            url = url.lower().strip()
            # Убираем .git в конце если есть
            if url.endswith(".git"):
                url = url[:-4]
            # Заменяем разные формы записи
            url = url.replace("https://", "").replace("http://", "").replace("git@", "")
            url = url.replace("github.com/", "github.com:")
            return url

        if normalize_url(current_url) != normalize_url(repo_url):
            log.info(
                f"Текущий репозиторий отличается от целевого: {current_url} vs {repo_url}"
            )
            return True
        try:
            # Получаем последний коммит из удаленного репозитория
            subprocess.run(
                ["git", "fetch", "origin"],
                cwd=target_dir,
                capture_output=True,
                check=True,
            )

            # Сравниваем локальный и удаленный коммит
            local_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            remote_commit = subprocess.run(
                ["git", "rev-parse", "origin/main"],  # или origin/master
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            if local_commit != remote_commit:
                log.info(
                    f"Репозиторий устарел: локальный {local_commit[:8]} != удаленный {remote_commit[:8]}"
                )
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
