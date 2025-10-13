import json
import random
from datetime import datetime, timedelta
from datetime import timezone as dt_tz
from typing import Any, Dict, Iterable, Optional, Tuple

from celery.utils.log import get_task_logger
from shapely.geometry import MultiPolygon, Point
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.geometry.base import BaseGeometry

log = get_task_logger(__name__)


def ensure_index(es, index: str) -> None:
    if es.indices.exists(index=index):
        return
    body = {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "properties": {
                "device_id": {"type": "keyword"},
                "mac": {"type": "keyword"},
                "mac_address": {"type": "keyword"},
                "user_api": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "location": {"type": "geo_point"},
                "latitude": {"type": "double"},
                "longitude": {"type": "double"},
                "signal_strength": {"type": "integer"},
                "network_type": {"type": "keyword"},
                "test_data": {"type": "boolean"},
                "test_tag": {"type": "keyword"},
                "inside_polygon": {"type": "boolean"},
                "polygon_id": {"type": "keyword"},
                "detected_at": {"type": "date"},
                "timestamp": {"type": "date"},
                "is_alert": {"type": "boolean"},
                "is_ignored": {"type": "boolean"},
                "folder_name": {"type": "keyword"},
                "system_folder_name": {"type": "keyword"},
            }
        },
    }
    es.indices.create(index=index, body=body)


def gen_mac() -> str:
    return ":".join(f"{random.randint(0, 255):02x}" for _ in range(6))


def rand_ts(days_back: int) -> datetime:
    now = datetime.now(dt_tz.utc)
    delta = timedelta(
        days=random.randint(0, max(days_back, 0)),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )
    return now - delta


def rand_point_in_polygon(poly: BaseGeometry) -> Point:
    minx, miny, maxx, maxy = poly.bounds
    for _ in range(300):
        p = Point(random.uniform(minx, maxx), random.uniform(miny, maxy))
        if poly.contains(p):
            return p
    return poly.centroid


def rand_point_outside(
    bounds: Tuple[float, float, float, float], exclude_poly: Optional[BaseGeometry]
) -> Point:
    minx, miny, maxx, maxy = bounds
    w = maxx - minx
    h = maxy - miny
    ext = 0.35
    eminx, emaxx = (minx - w * ext), (maxx + w * ext)
    eminy, emaxy = (miny - h * ext), (maxy + h * ext)
    for _ in range(800):
        p = Point(random.uniform(eminx, emaxx), random.uniform(eminy, emaxy))
        if exclude_poly is None or not exclude_poly.contains(p):
            return p
    return Point(emaxx, emaxy)


def make_doc(
    mac: str,
    device_id: str,
    point: Point,
    ts: datetime,
    inside: bool,
    polygon_id: Optional[str],
    test_tag: str,
    user_api_value: Optional[str],
) -> Dict[str, Any]:
    lat, lon = float(point.y), float(point.x)
    network = random.choice(["WiFi", "Bluetooth", "Cellular"])
    base = {
        "device_id": device_id,
        "mac": mac,
        "mac_address": mac,
        "user_phone_mac": mac,
        "location": {"lat": lat, "lon": lon},
        "latitude": lat,
        "longitude": lon,
        "signal_strength": random.randint(-90, -30),
        "network_type": network,
        "is_alert": random.random() < 0.05,
        "is_ignored": random.random() < 0.02,
        "folder_name": random.choice(["", "alpha", "beta", "gamma"]),
        "system_folder_name": random.choice(["", "sys-A", "sys-B", "sys-C"]),
        "timestamp": ts.isoformat(),
        "detected_at": ts.isoformat(),
        "test_data": True,
        "test_tag": test_tag,
        "inside_polygon": inside,
        "polygon_id": polygon_id,
    }
    if user_api_value:
        base["user_api"] = user_api_value
    return base


def parse_polygon(geojson: Dict[str, Any]) -> BaseGeometry:
    if geojson["type"] == "Polygon":
        return ShapelyPolygon(geojson["coordinates"][0])
    if geojson["type"] == "MultiPolygon":
        return MultiPolygon([ShapelyPolygon(p[0]) for p in geojson["coordinates"]])
    raise ValueError(f"Unsupported GeoJSON type: {geojson['type']}")


def generate_and_index(
    *,
    es,
    index: str,
    mac_count: int = 100,
    records_min: int = 3000,
    records_max: int = 4000,
    in_ratio: float = 0.2,
    days_back: int = 30,
    polygon_geojson: Optional[Dict[str, Any]] = None,
    polygon_bbox: Optional[Tuple[float, float, float, float]] = None,
    tag: str = "polygons_gen_v1",
    user_api_value: Optional[str] = None,
    seed: Optional[int] = None,
    chunk_size: int = 5000,
) -> Dict[str, Any]:
    if seed is not None:
        random.seed(seed)

    ensure_index(es, index)

    target_polygon = None
    bounds = None
    if polygon_geojson:
        target_polygon = parse_polygon(polygon_geojson)
        bounds = target_polygon.bounds
    else:
        if polygon_bbox:
            bounds = polygon_bbox
        else:
            bounds = (37.4, 55.5, 37.9, 55.9)

    macs = [gen_mac() for _ in range(mac_count)]

    total_docs = 0
    buf = []

    for mac in macs:
        n = random.randint(records_min, records_max)
        inside_n = int(n * in_ratio) if target_polygon is not None else 0
        outside_n = n - inside_n
        device_id = f"DEV-{mac.replace(':', '').upper()}"

        for _ in range(inside_n):
            pt = rand_point_in_polygon(target_polygon)
            ts = rand_ts(days_back)
            doc = make_doc(
                mac,
                device_id,
                pt,
                ts,
                True,
                polygon_geojson.get("id") if polygon_geojson else None,
                tag,
                user_api_value,
            )
            buf.append({"_index": index, "_source": doc})

        for _ in range(outside_n):
            pt = rand_point_outside(bounds, target_polygon)
            ts = rand_ts(days_back)
            doc = make_doc(
                mac,
                device_id,
                pt,
                ts,
                False,
                polygon_geojson.get("id") if polygon_geojson else None,
                tag,
                user_api_value,
            )
            buf.append({"_index": index, "_source": doc})

        total_docs += n

        if len(buf) >= chunk_size:
            from elasticsearch.helpers import bulk

            bulk(es, buf, raise_on_error=False, request_timeout=180)
            buf.clear()

    if buf:
        from elasticsearch.helpers import bulk

        bulk(es, buf, raise_on_error=False, request_timeout=180)

    return {"mac_count": mac_count, "total_docs": total_docs, "index": index}


def iter_docs(
    *,
    mac_count: int = 100,
    records_min: int = 3000,
    records_max: int = 4000,
    in_ratio: float = 0.2,
    days_back: int = 30,
    polygon_geojson: Optional[Dict[str, Any]] = None,
    polygon_bbox: Optional[Tuple[float, float, float, float]] = None,
    tag: str = "polygons_gen_v1",
    user_api_value: Optional[str] = None,
    seed: Optional[int] = None,
):
    """Генерировать синтетические документы по одному (без записи в ES)."""
    if seed is not None:
        random.seed(seed)

    target_polygon = None
    bounds = None
    if polygon_geojson:
        target_polygon = parse_polygon(polygon_geojson)
        bounds = target_polygon.bounds
    else:
        if polygon_bbox:
            bounds = polygon_bbox
        else:
            bounds = (37.4, 55.5, 37.9, 55.9)

    macs = [gen_mac() for _ in range(mac_count)]

    for mac in macs:
        n = random.randint(records_min, records_max)
        inside_n = int(n * in_ratio) if target_polygon is not None else 0
        outside_n = n - inside_n
        device_id = f"DEV-{mac.replace(':', '').upper()}"

        for _ in range(inside_n):
            pt = rand_point_in_polygon(target_polygon)
            ts = rand_ts(days_back)
            yield make_doc(
                mac,
                device_id,
                pt,
                ts,
                True,
                polygon_geojson.get("id") if polygon_geojson else None,
                tag,
                user_api_value,
            )

        for _ in range(outside_n):
            pt = rand_point_outside(bounds, target_polygon)
            ts = rand_ts(days_back)
            yield make_doc(
                mac,
                device_id,
                pt,
                ts,
                False,
                polygon_geojson.get("id") if polygon_geojson else None,
                tag,
                user_api_value,
            )
