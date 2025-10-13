# tasks_way.py
from os import getenv
from typing import Any, Dict, List

from celery.utils.log import get_task_logger
from celery_app import app
from es_writer import index_docs_to_way

log = get_task_logger(__name__)

cName = getenv("CELERY_C_TASK_NAME")
cQueue = getenv("CELERY_C_QUEUE_NAME")


@app.task(name=cName, queue=cQueue)
def ingest_way_serial(
    docs: List[Dict[str, Any]], *, chunk_size: int = 2000, refresh: str = "false"
) -> Dict[str, Any]:
    res = index_docs_to_way(docs, chunk_size=chunk_size, refresh=refresh)
    if res["errors_count"]:
        log.warning(
            "ES bulk had %s errors, sample=%s",
            res["errors_count"],
            res["errors_sample"],
        )
    return res
