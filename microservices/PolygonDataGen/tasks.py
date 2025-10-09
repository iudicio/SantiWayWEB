import os
from typing import Dict, Any, Optional, Tuple
from celery_app import app
from celery.utils.log import get_task_logger
from gen_core import iter_docs

log = get_task_logger(__name__)


TASK_NAME = os.getenv("CELERY_C_TASK_NAME", "polygons.generate_data")
TASK_QUEUE = os.getenv("CELERY_C_QUEUE_NAME", "polygon_gen")


@app.task(name=TASK_NAME, queue=TASK_QUEUE)
def generate_data_task(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ключи cfg (все необязательные, если не указано иное):
        - index_name: str (по умолчанию 'way')
        - mac_count: int (по умолчанию 100)
        - records_per_mac: [min:int, max:int] (по умолчанию [3000, 4000])
        - in_polygon_ratio: float (по умолчанию 0.2)
        - days_back: int (по умолчанию 30)
        - polygon_geojson: dict (GeoJSON Polygon/MultiPolygon)
        - polygon_bbox: [minx, miny, maxx, maxy], если полигона нет
        - tag: str (по умолчанию 'polygons_gen_v1')
        - user_api: str (необязательно)
        - seed: int (необязательно)
        - chunk_size: int (по умолчанию 5000)
        - es_url: str (необязательно; по умолчанию берётся из переменной окружения ES_URL)
    """
    index = cfg.get("index_name", "way")
    mac_count = int(cfg.get("mac_count", 100))
    rmin, rmax = cfg.get("records_per_mac", [3000, 4000])
    in_ratio = float(cfg.get("in_polygon_ratio", 0.2))
    days_back = int(cfg.get("days_back", 30))
    polygon_gj = cfg.get("polygon_geojson")
    bbox = cfg.get("polygon_bbox")
    if bbox and isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        bbox = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    else:
        bbox = None
    tag = cfg.get("tag", "polygons_gen_v1")
    user_api = cfg.get("user_api")
    seed = cfg.get("seed")
    send_batch_size = int(cfg.get("chunk_size", 5000))

    writer_task = os.getenv("ESWRITER_TASK_NAME", os.getenv("ES_WRITER_TASK_NAME", "esWriter"))
    writer_queue = os.getenv("ESWRITER_QUEUE_NAME", os.getenv("ES_WRITER_QUEUE_NAME", "esWriter_queue"))
    es_bulk_chunk = int(os.getenv("ESWRITER_BULK_CHUNK", "2000"))

    log.info(
        "Start generation: index=%s mac=%s records=[%s,%s] in_ratio=%s -> ESWriter task=%s queue=%s",
        index, mac_count, rmin, rmax, in_ratio, writer_task, writer_queue,
    )

    total_docs = 0
    buf = []

    for doc in iter_docs(
        mac_count=mac_count,
        records_min=int(rmin),
        records_max=int(rmax),
        in_ratio=in_ratio,
        days_back=days_back,
        polygon_geojson=polygon_gj,
        polygon_bbox=bbox,
        tag=tag,
        user_api_value=user_api,
        seed=seed,
    ):
        buf.append(doc)
        total_docs += 1
        if len(buf) >= send_batch_size:
            app.send_task(writer_task, args=[buf], kwargs={"chunk_size": es_bulk_chunk}, queue=writer_queue)
            buf = []

    if buf:
        app.send_task(writer_task, args=[buf], kwargs={"chunk_size": es_bulk_chunk}, queue=writer_queue)

    result = {
        "mac_count": mac_count,
        "total_docs": total_docs,
        "index": index, 
        "published_batches": max(1, (total_docs + send_batch_size - 1) // send_batch_size)
    }
    log.info("Generation published to ESWriter: %s", result)
    return result
