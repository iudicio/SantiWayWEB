"""
Health Check Endpoints для Kubernetes Probes

Добавить в urls.py:
    from api.health import urlpatterns as health_urls
    urlpatterns += health_urls
"""

from django.http import JsonResponse
from django.db import connection
from django.urls import path


def liveness(request):
    """
    Liveness Probe - проверяет что Django процесс жив
    
    НЕ проверяет внешние зависимости (DB, ES, etc.)
    Если этот endpoint не отвечает — Kubernetes перезапустит контейнер
    """
    return JsonResponse({
        "status": "alive",
    })


def readiness(request):
    """
    Readiness Probe - проверяет готовность принимать трафик
    
    Проверяет все критичные зависимости:
    - PostgreSQL
    - Elasticsearch
    - и т.д.
    
    Если не готов — Kubernetes уберёт pod из балансировки (Service)
    """
    checks = {}
    all_ok = True
    
    # Проверка PostgreSQL
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        all_ok = False
    
    # Проверка Elasticsearch (раскомментировать если используется)
    # try:
    #     from elasticsearch import Elasticsearch
    #     from django.conf import settings
    #     es = Elasticsearch([settings.ELASTICSEARCH_HOST])
    #     if not es.ping():
    #         raise Exception("ES ping failed")
    #     checks["elasticsearch"] = "ok"
    # except Exception as e:
    #     checks["elasticsearch"] = f"error: {str(e)}"
    #     all_ok = False
    
    status_code = 200 if all_ok else 503
    return JsonResponse({
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
    }, status=status_code)


# URL patterns — импортировать в основной urls.py
urlpatterns = [
    path("health/live/", liveness, name="health-liveness"),
    path("health/ready/", readiness, name="health-readiness"),
]

