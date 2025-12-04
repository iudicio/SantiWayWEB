from typing import List, Dict, Any
from celery_app import app
from celery.utils.log import get_task_logger
from ch_writer import insert_docs_to_way
from os import getenv

log = get_task_logger(__name__)

cName = getenv("CELERY_C_TASK_NAME")
cQueue = getenv("CELERY_C_QUEUE_NAME")

@app.task(name=cName, queue=cQueue)
def ingest_way_serial(docs: List[Dict[str, Any]], *, chunk_size: int = 2000) -> Dict[str, Any]:
    """
    Celery task для записи данных в ClickHouse.

    Args:
        docs: Список документов для вставки
        chunk_size: Размер батча

    Returns:
        Результат операции с количеством вставленных документов и ошибками
    """
    log.info(f"Received {len(docs)} documents for ClickHouse ingestion")

    res = insert_docs_to_way(docs, chunk_size=chunk_size)

    if res["errors_count"]:
        log.warning("CH bulk had %s errors, sample=%s", res["errors_count"], res["errors_sample"])
    else:
        log.info(f"Successfully inserted {res['inserted']} documents to ClickHouse")

    return res
