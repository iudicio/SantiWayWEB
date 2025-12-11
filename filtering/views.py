from os import getenv
import logging

from celery import Celery
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.conf import settings

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import NotFoundError

from .serializers import DeviceSearchRequestSerializer, SearchQuerySerializer
from .models import SearchQuery
from users.models import APIKey, User
from api.auth import APIKeyAuthentication
from api.permissions import HasAPIKey


log = logging.getLogger(__name__)


# ---- НАСТРОЙКИ ES ИЗ settings/env ----
ES_HOST = getattr(settings, "ELASTICSEARCH_DSN", getenv("ES_URL"))  # может быть URL-строкой или списком
ES_USER = getenv("ES_USER")
ES_PASSWORD = getenv("ES_PASSWORD")

ES_INDEX = getattr(settings, "ES_INDEX", "way")
ES_LOCATION_FIELD = getattr(settings, "ES_LOCATION_FIELD", "location")
ES_TIMESTAMP_FIELD = getattr(settings, "ES_TIMESTAMP_FIELD", "detected_at")

es = None


def get_es():
    """
    Возвращает готовый Elasticsearch client или None, если не сконфигурировано/ошибка.
    Использует:
      - ELASTICSEARCH_DSN (settings) ИЛИ ES_URL (env),
      - ES_USER/ES_PASSWORD (env) при наличии.
    """
    global es
    if es is not None:
        return es
    if not ES_HOST:
        log.warning("Elasticsearch DSN is not set (ELASTICSEARCH_DSN/ES_URL).")
        return None
    try:
        # ES_HOST может быть строкой вида "http://elastic:9200" ИЛИ списком хостов
        kwargs = {}
        if ES_USER and ES_PASSWORD:
            kwargs["basic_auth"] = (ES_USER, ES_PASSWORD)
        es_client = Elasticsearch(ES_HOST, **kwargs)
        # быстрая проверка соединения, чтобы не держать "битый" клиент
        es_client.info()
        es = es_client
        return es
    except Exception as e:
        log.exception("Elasticsearch init failed: %s", e)
        es = None
        return None


def _get_search_user(request):
    """
    Определяем, для какого Django-пользователя сохранять фильтрацию.

    1) Если есть request.user и он аутентифицирован -> используем его.
    2) Если используется API-ключ:
         - request.auth это либо объект APIKey, либо сам UUID ключа
         - ищем через User.api_keys (ManyToMany).
    """
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user

    auth = getattr(request, "auth", None)

    api_key_obj = None

    # Вариант 1: APIKeyAuthentication кладёт в request.auth САМ объект APIKey
    if isinstance(auth, APIKey):
        api_key_obj = auth

    # Вариант 2: в request.auth лежит строка/UUID ключа
    elif auth:
        try:
            api_key_obj = APIKey.objects.get(key=auth)
        except APIKey.DoesNotExist:
            api_key_obj = None

    if api_key_obj is None:
        return None

    # Ищем пользователя, к которому привязан этот APIKey через ManyToMany api_keys
    user = User.objects.filter(api_keys=api_key_obj).first()
    return user


def _save_last_search_query(request, items, polygons):
    user = _get_search_user(request)
    if user is None:
        return

    params = {
        "query_params": request.query_params.dict(),
        "polygons": polygons or [],
    }

    monitored_macs = [
        row.get("device_id")
        for row in items
        if isinstance(row, dict) and row.get("device_id")
    ]

    # ВАЖНО: сначала удаляем все прошлые фильтрации этого пользователя
    SearchQuery.objects.filter(user=user).delete()

    # Потом создаём одну новую
    SearchQuery.objects.create(
        user=user,
        params=params,
        results=items,
        monitored_macs=monitored_macs,
    )


def _geo_filters_from_polygons(polygons):
    """
    На вход ожидаем polygons в формате тела запроса:
    {"polygons":[{"points":[[lon,lat], ...]}, ...]}

    Возвращаем список ES-фильтров:
      - один geo_polygon, если полигон один
      - bool.should из нескольких geo_polygon, если полигонов >1
    """
    geo_filters = []
    if not polygons:
        return geo_filters

    for poly in polygons:
        points = poly.get("points") or []
        # Если пришёл "мультиконтур": [ [ring1...], [ring2...] ], берём внешний контур как первый
        if points and isinstance(points[0][0], (int, float)):
            # один контур
            ring = points
        else:
            # первый контур внешняя граница
            ring = points[0] if points else []

        if not ring:
            continue

        # Elasticsearch ждёт [lat, lon] или [lon, lat]?
        # Для geo_polygon points -> [lon, lat]
        geo_filters.append({
            "geo_polygon": {
                ES_LOCATION_FIELD: {"points": [{"lon": p[0], "lat": p[1]} for p in ring]}
            }
        })

    if len(geo_filters) == 1:
        return [geo_filters[0]]

    # Несколько полигонов -> объединяем через should
    return [{
        "bool": {
            "should": geo_filters,
            "minimum_should_match": 1
        }
    }]


def _parse_polygons_from_body(request):
    """
    Ждём в теле JSON: {"polygons":[{"points":[[lon,lat], ...]}, ...]}
    Возвращает список колец (каждое — список [lon, lat]).
    """
    data = request.data if isinstance(request.data, dict) else {}
    polys = data.get("polygons") or []
    rings = []
    for poly in polys if isinstance(polys, list) else []:
        pts = poly.get("points") if isinstance(poly, dict) else None
        if not pts:
            continue
        ring = pts if (isinstance(pts, list) and pts and isinstance(pts[0][0], (int, float))) else (pts[0] if pts else [])
        if len(ring) >= 3:
            rings.append(ring)
    return rings


def _point_in_ring(lon, lat, ring):
    # включаем попадание на границу
    if ring and ring[0] == ring[-1]:
        ring = ring[:-1]
    n = len(ring)
    if n < 3:
        return False
    # попадание на ребро
    for i in range(n):
        x1,y1 = ring[i]; x2,y2 = ring[(i+1)%n]
        dx,dy = x2-x1, y2-y1
        dxp,dyp = lon-x1, lat-y1
        cross = dx*dyp - dy*dxp
        if abs(cross) < 1e-12:
            dot = dxp*dx + dyp*dy
            if -1e-12 <= dot <= dx*dx + dy*dy + 1e-12:
                return True
    # ray casting
    inside = False; j = n-1
    for i in range(n):
        xi,yi = ring[i]; xj,yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-30) + xi):
            inside = not inside
        j = i
    return inside


def _point_in_any_polygon(lon, lat, rings):
    return any(_point_in_ring(lon, lat, r) for r in rings)


def _build_es_filters_from_query(query_params):
    """Ровно как у тебя было, но игнорим служебные size; polygons здесь не используется вообще."""
    must_filters = []
    for field, value in query_params.items():
        if field in ("size",):
            continue
        if "__" in field:
            field_name, op = field.split("__", 1)
            if op in ["gte", "lte", "gt", "lt"]:
                must_filters.append({"range": {field_name: {op: value}}})
                continue
        if "," in value:
            must_filters.append({"terms": {field: value.split(",")}})
        else:
            must_filters.append({"term": {field: value}})
    return must_filters


def _run_search_with_optional_polygons(request, polygons=None):
    """
    Выполняет запрос к Elasticsearch с учётом:
      - обычных фильтров из query-параметров;
      - (опционально) гео-фильтра по полигонам из body;
    и возвращает ТОЛЬКО уникальные устройства (MAC), где по каждому MAC берётся
    САМАЯ ПОЗДНЯЯ запись (по ES_TIMESTAMP_FIELD).

    GET /api/filtering/  -> polygons=None
    POST /api/filtering/ -> polygons из тела {"polygons":[{"points":[[lon,lat], ...]}, ...]}
    """
    es = get_es()
    if es is None:
        return Response({"error": "Elasticsearch is not configured"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)

    # обычные фильтры из query-параметров
    must_filters = _build_es_filters_from_query(request.query_params)

    # гео-фильтры из polygons (формат как в теле запроса)
    geo_filters = _geo_filters_from_polygons(polygons or [])

    filters = []
    if must_filters:
        filters.extend(must_filters)
    if geo_filters:
        filters.extend(geo_filters)

    if filters:
        query = {"bool": {"filter": filters}}
    else:
        query = {"match_all": {}}

    # Параметр size теперь трактуем как: "сколько УНИКАЛЬНЫХ MAC'ов вернуть максимум"
    uniq_size = min(
        max(int(request.query_params.get("size", 300)), 1),
        10000
    )

    body = {
        "size": 0,  # документы в hits нам не нужны, работаем только через агрегации
        "query": query,
        "aggs": {
            "by_device": {
                "terms": {
                    # поле с MAC адресом устройства
                    # если у тебя device_id это keyword-поле, оставь так;
                    # если text+keyword, нужно "device_id.keyword"
                    "field": "device_id",
                    "size": uniq_size
                },
                "aggs": {
                    "latest": {
                        "top_hits": {
                            "size": 1,
                            "sort": [
                                {
                                    ES_TIMESTAMP_FIELD: {
                                        "order": "desc"
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        }
    }

    try:
        res = es.search(index=ES_INDEX, body=body)
    except NotFoundError:
        items = []
        # даже если пусто — можно сохранить пустую фильтрацию
        _save_last_search_query(request, items, polygons)
        return Response(items, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Elasticsearch query failed: {e}"},
                        status=status.HTTP_502_BAD_GATEWAY)

    # Достаём по одному _source из каждого бакета (последняя запись по MAC)
    buckets = (
        res.get("aggregations", {})
        .get("by_device", {})
        .get("buckets", [])
    )

    items = []
    for b in buckets:
        hits = b.get("latest", {}).get("hits", {}).get("hits", [])
        if not hits:
            continue
        items.append(hits[0]["_source"])

    # Сохраняем последнюю фильтрацию пользователя
    _save_last_search_query(request, items, polygons)

    return Response(items, status=status.HTTP_200_OK)


class FilteringViewSet(viewsets.ViewSet):
    """
    Фильтрация устройств по запросу:
      - GET /api/filtering/ — без полигонов;
      - POST /api/filtering/ — с полигонами в теле запроса.
    """
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasAPIKey]

    # GET /api/filtering/  (без полигонов, чисто как раньше)
    def list(self, request, *args, **kwargs):
        # polygons здесь НЕ поддерживаем
        return _run_search_with_optional_polygons(request, polygons=None)

    #POST /api/filtering/  (полигоны в body, остальные фильтры — в query)
    def create(self, request, *args, **kwargs):
        # ждём формата: {"polygons":[{"points":[[lon,lat], ...]}, ...]}
        data = request.data if isinstance(request.data, dict) else {}
        polygons = data.get("polygons") or []
        return _run_search_with_optional_polygons(request, polygons=polygons)