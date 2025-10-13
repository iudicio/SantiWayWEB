from os import getenv
from typing import List, Dict, Any
from elasticsearch import Elasticsearch
from celery_app import app
from celery.utils.log import get_task_logger

log = get_task_logger(__name__)

ES_HOST = getenv("ES_HOST")
ES_CLIENT = Elasticsearch(hosts=ES_HOST)

cName1 = getenv("CELERY_C_TASK_NAME1")
cName2 = getenv("CELERY_C_TASK_NAME2")
cQueue = getenv("CELERY_C_QUEUE_NAME")


@app.task(name=cName1, queue=cQueue)
def getDevices(data: list[str]) -> list[str]:
    global ES_CLIENT

    query = {
        "query": {"bool": {"filter": [{"terms": {"user_api": data["api_keys"]}}]}},
        "size": 0,
        "_source": False,
        "aggs": {"unique_macs": {"terms": {"field": "user_phone_mac", "size": 100000}}},
    }

    result = ES_CLIENT.search(index="way", body=query)
    macs = [b["key"] for b in result["aggregations"]["unique_macs"]["buckets"]]
    return macs


@app.task(name=cName2, queue=cQueue)
def getFolders(data: dict) -> list[str]:
    global ES_CLIENT

    api_keys = data.get("api_keys", [])
    devices = data.get("devices", [])

    query = {
        "query": {
            "bool": {
                "filter": [
                    {"terms": {"user_api": api_keys}},
                    {"terms": {"user_phone_mac": devices}},
                ]
            }
        },
        "size": 0,
        "aggs": {"unique_folders": {"terms": {"field": "folder_name", "size": 100000}}},
    }

    res = ES_CLIENT.search(index="way", body=query)
    folders = [b["key"] for b in res["aggregations"]["unique_folders"]["buckets"]]
    return folders
