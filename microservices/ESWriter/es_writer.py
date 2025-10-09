# es_writer_way
from os import getenv
from typing import Any, Dict, List

from elasticsearch import Elasticsearch, helpers

WAY_ALIAS = "way"

ES_HOST = getenv("ES_HOST")
ES_CLIENT = Elasticsearch(hosts=ES_HOST)


def index_docs_to_way(
    docs: List[Dict[str, Any]], *, chunk_size: int = 2000, refresh: str = "false"
) -> Dict[str, Any]:
    """Пишем список JSON-объектов в alias 'way'. _id не задаём — ES сам генерит."""
    if not isinstance(docs, list):
        raise ValueError("docs must be a list of JSON objects")

    actions = ({"_op_type": "index", "_index": WAY_ALIAS, "_source": d} for d in docs)

    ok, errors = helpers.bulk(
        ES_CLIENT,
        actions,
        chunk_size=chunk_size,
        request_timeout=120,
        raise_on_error=False,
        refresh=refresh,  # "false" | "wait_for"
    )
    return {"indexed": ok, "errors_count": len(errors), "errors_sample": errors[:5]}
