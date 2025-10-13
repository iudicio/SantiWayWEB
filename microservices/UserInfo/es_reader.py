from os import getenv
from typing import Any, Dict, List

from elasticsearch import Elasticsearch

WAY_ALIAS = "way"

ES_HOST = getenv("ES_HOST")
ES_CLIENT = Elasticsearch(hosts=ES_HOST)


def getDevices(user_apis: list[str]) -> list[str]:
    global ES_CLIENT
    query = {
        "query": {"bool": {"filter": [{"terms": {"user_api": user_apis}}]}},
        "size": 0,  # не нужно получать сами документы
        "aggs": {
            "unique_macs": {
                "terms": {
                    "field": "user_phone_mac.keyword",  # .keyword — если поле текстовое
                    "size": 100,  # максимум уникальных значений
                }
            }
        },
    }

    result = ES_CLIENT.search(index="way", body=query)
    macs = [b["key"] for b in result["aggregations"]["unique_macs"]["buckets"]]
    return macs


def getFolders(api_device_pairs: list[tuple[str, str]]) -> list[str]:
    global ES_CLIENT
    should_pairs = [
        {
            "bool": {
                "must": [
                    {"term": {"api_key.keyword": api_key}},
                    {"term": {"device.keyword": device}},
                ]
            }
        }
        for api_key, device in api_device_pairs
    ]

    query = {
        "query": {"bool": {"should": should_pairs, "minimum_should_match": 1}},
        "size": 0,
        "aggs": {
            "unique_folders": {
                "terms": {"field": "folder_name.keyword", "size": 100000}
            }
        },
    }

    res = ES_CLIENT.search(index="way", body=query)
    folders = [b["key"] for b in res["aggregations"]["unique_folders"]["buckets"]]
    return folders
