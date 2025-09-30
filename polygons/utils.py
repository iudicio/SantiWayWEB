"""
Утилиты для работы с геометрией полигонов
"""
import math
from typing import List, Tuple, Dict, Any
from shapely.geometry import Polygon as ShapelyPolygon, Point
from shapely.ops import transform
from functools import partial
import pyproj
from elasticsearch import Elasticsearch
from django.conf import settings


def calculate_polygon_area(coordinates: List[List[float]]) -> float:
    """
    Точная площадь многоугольника в км² через проекцию в метры.

    1) Формируем Shapely-полигон из координат (lon, lat),
    2) Проецируем в локальную равновеликую проекцию (азимутальную эквидистантную)
       с центром в центре масс полигона,
    3) Возвращаем площадь в км².
    """
    try:
        if not coordinates:
            return 0.0

        ring = coordinates
        if ring[0] != ring[-1]:
            ring = ring + [ring[0]]

        poly = ShapelyPolygon(ring)
        if not poly.is_valid or poly.is_empty:
            return 0.0

        centroid = poly.centroid
        lon0, lat0 = float(centroid.x), float(centroid.y)

        aeqd = pyproj.CRS.from_proj4(
            f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +x_0=0 +y_0=0 +units=m +no_defs"
        )
        wgs84 = pyproj.CRS.from_epsg(4326)

        project = pyproj.Transformer.from_crs(wgs84, aeqd, always_xy=True).transform
        poly_m = transform(project, poly)

        area_km2 = float(poly_m.area) / 1_000_000.0
        return round(area_km2, 6)
    except Exception:
        return 0.0


def validate_polygon_geometry(geometry: Dict[str, Any]) -> bool:
    """
    Валидирует геометрию полигона
    
    Args:
        geometry: GeoJSON геометрия
    
    Returns:
        True если геометрия валидна
    """
    try:
        if geometry.get('type') != 'Polygon':
            return False
        
        coordinates = geometry.get('coordinates', [])
        if not coordinates or len(coordinates) == 0:
            return False
        
        # Проверяем внешнее кольцо
        outer_ring = coordinates[0]
        if len(outer_ring) < 4:  # Минимум 4 точки (замкнутый полигон)
            return False
        
        # Проверяем, что первая и последняя точки совпадают
        if outer_ring[0] != outer_ring[-1]:
            return False
        
        # Проверяем координаты
        for coord in outer_ring:
            if len(coord) != 2:
                return False
            lon, lat = coord
            if not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
                return False
        
        return True
        
    except Exception:
        return False


def point_in_polygon(point: Tuple[float, float], polygon_coordinates: List[List[float]]) -> bool:
    """
    Проверяет, находится ли точка внутри полигона
    
    Args:
        point: (longitude, latitude)
        polygon_coordinates: Список координат полигона
    
    Returns:
        True если точка внутри полигона
    """
    try:
        polygon = ShapelyPolygon(polygon_coordinates)
        point_obj = Point(point[0], point[1])
        return polygon.contains(point_obj)
        
    except Exception:
        return False


def simplify_polygon(coordinates: List[List[float]], tolerance: float = 0.0001) -> List[List[float]]:
    """
    Упрощает полигон, удаляя избыточные точки
    
    Args:
        coordinates: Координаты полигона
        tolerance: Толерантность упрощения
    
    Returns:
        Упрощенные координаты
    """
    try:
        polygon = ShapelyPolygon(coordinates)
        simplified = polygon.simplify(tolerance, preserve_topology=True)
        
        # Возвращаем координаты внешнего кольца
        return list(simplified.exterior.coords)
        
    except Exception:
        return coordinates


def get_polygon_bounds(coordinates: List[List[float]]) -> Dict[str, float]:
    """
    Получает границы полигона (bounding box)
    
    Args:
        coordinates: Координаты полигона
    
    Returns:
        Словарь с границами {min_lon, max_lon, min_lat, max_lat}
    """
    try:
        polygon = ShapelyPolygon(coordinates)
        bounds = polygon.bounds
        
        return {
            'min_lon': bounds[0],
            'min_lat': bounds[1],
            'max_lon': bounds[2],
            'max_lat': bounds[3]
        }
        
    except Exception:
        return {
            'min_lon': 0,
            'min_lat': 0,
            'max_lon': 0,
            'max_lat': 0
        }


def search_devices_in_polygon(geometry: Dict[str, Any], user_api_key: str = None) -> List[Dict[str, Any]]:
    """
    Поиск устройств в полигоне через Elasticsearch
    
    Args:
        geometry: GeoJSON геометрия полигона
        user_api_key: API ключ пользователя для фильтрации
    
    Returns:
        Список найденных устройств
    """
    try:
        es = Elasticsearch([settings.ELASTICSEARCH_DSN])
        
        coordinates = geometry.get('coordinates', [])
        if not coordinates or len(coordinates) == 0:
            return []
        
        outer_ring = coordinates[0]
        

        lons = [point[0] for point in outer_ring]
        lats = [point[1] for point in outer_ring]
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)
        
        query = {
            "query": {
                "bool": {
                    "should": [
                        # latitude, longitude
                        {
                            "bool": {
                                "must": [
                                    {
                                        "range": {
                                            "longitude": {
                                                "gte": min_lon,
                                                "lte": max_lon
                                            }
                                        }
                                    },
                                    {
                                        "range": {
                                            "latitude": {
                                                "gte": min_lat,
                                                "lte": max_lat
                                            }
                                        }
                                    }
                                ]
                            }
                        },
                        # location.lat, location.lon
                        {
                            "bool": {
                                "must": [
                                    {
                                        "range": {
                                            "location.lon": {
                                                "gte": min_lon,
                                                "lte": max_lon
                                            }
                                        }
                                    },
                                    {
                                        "range": {
                                            "location.lat": {
                                                "gte": min_lat,
                                                "lte": max_lat
                                            }
                                        }
                                    }
                                ]
                            }
                        }
                    ],
                    "minimum_should_match": 1
                }
            },
            "size": 1000
        }
        
        if user_api_key:
            if "must" not in query["query"]["bool"]:
                query["query"]["bool"]["must"] = []
            query["query"]["bool"]["must"].append({
                "term": {"user_api.keyword": user_api_key}
            })
        
        response = es.search(index="way", body=query)
        
        devices = []
        for hit in response["hits"]["hits"]:
            device = hit["_source"]
            
            if "latitude" in device and "longitude" in device:
                # latitude, longitude
                lat, lon = device["latitude"], device["longitude"]
            elif "location" in device and isinstance(device["location"], dict):
                # location.lat, location.lon
                lat, lon = device["location"]["lat"], device["location"]["lon"]
            else:
                continue  # Без координат
            
            if point_in_polygon((lon, lat), outer_ring):
                devices.append(device)
        
        return devices
        
    except Exception as e:
        print(f"Ошибка поиска устройств в полигоне: {e}")
        return []
