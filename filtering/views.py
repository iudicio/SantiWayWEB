import logging
from os import getenv

from django.conf import settings

from celery import Celery
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import NotFoundError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from api.auth import APIKeyAuthentication
from api.permissions import HasAPIKey

from .models import SearchQuery
from .serializers import DeviceSearchRequestSerializer, SearchQuerySerializer

log = logging.getLogger(__name__)


# ---- НАСТРОЙКИ ES ИЗ settings/env ----
ES_HOST = getattr(
    settings, "ELASTICSEARCH_DSN", getenv("ES_URL")
)  # может быть URL-строкой или списком
ES_USER = getenv("ES_USER")
ES_PASSWORD = getenv("ES_PASSWORD")

ES_INDEX = getattr(settings, "ES_INDEX", "way")
ES_LOCATION_FIELD = getattr(settings, "ES_LOCATION_FIELD", "location")
ES_TIMESTAMP_FIELD = getattr(settings, "ES_TIMESTAMP_FIELD", "timestamp")

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


def _geo_filters_from_polygons(polygons):
    """
    Строим список geo-фильтров. Если поле geo_point — используем geo_polygon.
    Если geo_shape — используем geo_shape with polygon.
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
        geo_filters.append(
            {
                "geo_polygon": {
                    ES_LOCATION_FIELD: {
                        "points": [{"lon": p[0], "lat": p[1]} for p in ring]
                    }
                }
            }
        )

    if len(geo_filters) == 1:
        return [geo_filters[0]]

    # Несколько полигонов -> объединяем через should
    return [{"bool": {"should": geo_filters, "minimum_should_match": 1}}]


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
        ring = (
            pts
            if (isinstance(pts, list) and pts and isinstance(pts[0][0], (int, float)))
            else (pts[0] if pts else [])
        )
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
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        dxp, dyp = lon - x1, lat - y1
        cross = dx * dyp - dy * dxp
        if abs(cross) < 1e-12:
            dot = dxp * dx + dyp * dy
            if -1e-12 <= dot <= dx * dx + dy * dy + 1e-12:
                return True
    # ray casting
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-30) + xi
        ):
            inside = not inside
        j = i
    return inside


def _point_in_any_polygon(lon, lat, rings):
    return any(_point_in_ring(lon, lat, r) for r in rings)


def _build_es_filters_from_query(query_params):
    """Ровно как у тебя было, но игнорим служебные size; polygons здесь не используется вообще."""
    must_filters = []
    for field, value in query_params.items():
        if field in ("size",):  # важно: polygons тут не ожидаем
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


def _run_search_and_optional_polygon_postfilter(request, rings):
    """Общий метод: дергаем ES по query-парам, затем (если есть rings) — сужаем по полигонам."""
    es = get_es()
    if es is None:
        return Response(
            {"error": "Elasticsearch is not configured"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    must_filters = _build_es_filters_from_query(request.query_params)
    query = (
        {"query": {"bool": {"filter": must_filters}}}
        if must_filters
        else {"query": {"match_all": {}}}
    )
    size = min(max(int(request.query_params.get("size", 300)), 1), 10000)

    try:
        res = es.search(index=ES_INDEX, body=query, size=size)
    except NotFoundError:
        return Response([], status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Elasticsearch query failed: {e}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    items = [h["_source"] for h in res["hits"]["hits"]]

    # пост-фильтр по полигонам (если даны)
    if rings:
        filtered = []
        for row in items:
            loc = row.get(ES_LOCATION_FIELD)
            if isinstance(loc, (list, tuple)) and len(loc) == 2:
                lon, lat = float(loc[0]), float(loc[1])
            else:
                lon, lat = row.get("longitude"), row.get("latitude")
                if lon is None or lat is None:
                    continue
                lon, lat = float(lon), float(lat)
            if _point_in_any_polygon(lon, lat, rings):
                filtered.append(row)
        items = filtered

    return Response(items, status=status.HTTP_200_OK)


class FilteringViewSet(viewsets.ViewSet):
    """
    Список/поиск + расширенная ручка /search с полигонами и мониторингом MAC.
    """

    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasAPIKey]

    # GET /api/filtering/  (без полигонов, чисто как раньше)
    def list(self, request, *args, **kwargs):
        # polygons здесь НЕ поддерживаем
        rings = []  # принципиально пусто
        return _run_search_and_optional_polygon_postfilter(request, rings)

    # NEW: POST /api/filtering/  (полигоны в body, остальные фильтры — в query)
    def create(self, request, *args, **kwargs):
        rings = _parse_polygons_from_body(request)  # только из тела!
        return _run_search_and_optional_polygon_postfilter(request, rings)

    """
    # РАСШИРЕННЫЙ поиск
    @action(detail=False, methods=["POST"], url_path="search")
    def search_devices(self, request):
        es = get_es()
        if es is None:
            return Response({"error": "Elasticsearch is not configured"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        s = DeviceSearchRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        params = s.validated_data

        must = []
        should = []
        filters = []

        # Базовые списки
        if params["api_keys"]:
            must.append({"terms": {"api_key": params["api_keys"]}})
        if params["devices"]:
            must.append({"terms": {"device_id": params["devices"]}})
        if params["folders"]:
            must.append({"terms": {"folder_id": params["folders"]}})

        # Время
        time_range = {}
        if params.get("time_from"):
            time_range["gte"] = params["time_from"].isoformat()
        if params.get("time_to"):
            time_range["lte"] = params["time_to"].isoformat()
        if time_range:
            filters.append({"range": {ES_TIMESTAMP_FIELD: time_range}})

        # Тип устройства
        if params.get("device_type"):
            filters.append({"term": {"device_type": params["device_type"]}})

        # Флаги
        if params.get("is_alarm") is not None:
            filters.append({"term": {"is_alarm": params["is_alarm"]}})
        if params.get("is_ignored") is not None:
            filters.append({"term": {"is_ignored": params["is_ignored"]}})

        # Имя (точно/префикс)
        if params.get("name"):
            # точный match + префикс — через should
            should.append({"term": {"name.keyword": params["name"]}})
            should.append({"match_phrase_prefix": {"name": params["name"]}})

        # MAC фильтр (обычный)
        if params["macs"]:
            filters.append({"terms": {"mac": [m.lower() for m in params["macs"]]}})

        # Полигоны
        polygon_filters = _geo_filters_from_polygons(params.get("polygons", []))
        filters.extend(polygon_filters)

        bool_query = {"filter": filters}
        if must:
            bool_query["must"] = must
        if should:
            bool_query["should"] = should
            bool_query["minimum_should_match"] = 1

        body = {"query": {"bool": bool_query}}

        size = int(params.get("limit", 300))
        size = min(max(size, 1), 10000)

        try:
            res = es.search(index=ES_INDEX, body=body, size=size)
            hits = [h["_source"] for h in res["hits"]["hits"]]
        except NotFoundError:
            hits = []
        except Exception as e:
            return Response({"error": f"Elasticsearch query failed: {e}"}, status=status.HTTP_502_BAD_GATEWAY)

        # Мониторинг MAC в полигонах (в разрезе monitor_macs)
        monitoring = {}
        monitor_list = [m.lower() for m in params.get("monitor_macs", [])]
        if monitor_list and polygon_filters:
            # Берём только совпавшие с полигонами хиты и группируем по MAC из monitor_list
            for row in hits:
                mac = (row.get("mac") or "").lower()
                if mac in monitor_list:
                    monitoring.setdefault(mac, []).append(row)

        # Сохранение запроса/результатов (первые 300)
        saved = None
        if params.get("save_query", True) and request.user.is_authenticated:
            saved = SearchQuery.objects.create(
                user=request.user,
                params=params,
                results=hits[:300],
                monitored_macs=monitor_list,
                export_status=SearchQuery.FileStatus.PENDING,
                paid=getattr(request.user, "paid", False) if hasattr(request.user, "paid") else False,
            )

        payload = {
            "count": len(hits),
            "items": hits,
            "monitoring": monitoring,   # map: mac -> [items...]
            "saved_query": SearchQuerySerializer(saved).data if saved else None,
            "es_query": body,           # удобно для отладки фронту/бэку
        }
        return Response(payload, status=status.HTTP_200_OK)
        """
