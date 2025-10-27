import logging
from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apkbuilder.models import APKBuild

log = logging.getLogger(__name__)

TTL_HOURS = 24


def delete_background_task():
    """
    Каждую 30 минут:
    - Находит APKBuild с apk_file != NULL и "старше 2 минут":
        - если completed_at есть — сравниваем его,
        - иначе берём created_at.
    - Удаляет файл из стораджа и запись из БД.
    - Печатает сводку по API-ключам.
    """
    now_utc = timezone.now()
    cutoff_utc = now_utc - timedelta(hours=TTL_HOURS)

    now_local = timezone.localtime(now_utc)
    cutoff_local = timezone.localtime(cutoff_utc)

    # кандидаты к удалению: есть файл, и (completed_at < cutoff) OR (completed_at is NULL and created_at < cutoff)
    candidates = (
        APKBuild.objects.filter(apk_file__isnull=False)
        .filter(
            Q(completed_at__lt=cutoff_utc)
            | (Q(completed_at__isnull=True) & Q(created_at__lt=cutoff_utc))
        )
        .only("id", "apk_file", "api_key_id", "created_at", "completed_at", "status")
        .iterator(chunk_size=500)
    )

    per_key_deleted = defaultdict(int)
    total_deleted = 0

    for build in candidates:
        with transaction.atomic():
            if build.apk_file:
                build.apk_file.delete(save=False)  # удаляет физически
            per_key_deleted[build.api_key_id] += 1
            build.delete()
            total_deleted += 1

    if total_deleted == 0:
        msg = (
            f"[cron] {now_local:%Y-%m-%d %H:%M:%S} очистка APK: ничего не удалено "
            f"(cutoff={cutoff_local.isoformat()}, ttl={TTL_HOURS}h)"
        )
        print(msg)
        log.info(msg)
        return

    lines = [
        f"[cron] {now_local:%Y-%m-%d %H:%M:%S} очистка APK: "
        f"удалено всего {total_deleted} шт. (cutoff={cutoff_local.isoformat()}, ttl={TTL_HOURS}h)"
    ]
    for k, n in per_key_deleted.items():
        lines.append(f"  - api_key_id={k}: {n}")
    summary = "\n".join(lines)
    print(summary)
    log.info(summary)
