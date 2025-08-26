from rest_framework import viewsets, mixins
from rest_framework.response import Response
from .serializers import DeviceSerializer
from elasticsearch import Elasticsearch

es = Elasticsearch(hosts=["http://localhost:9200"])
INDEX_PREFIX = "way-*"

class DeviceViewSet(viewsets):
    def list(self, request, *args, **kwargs):
        must_filters = []

        for field, value in request.query_params.items():
            # Диапазоны (например: ?timestamp__gte=2025-01-01T00:00:00)
            if "" in field:
                field_name, op = field.split("", 1)
                if op in ["gte", "lte", "gt", "lt"]:
                    must_filters.append({
                        "range": {field_name: {op: value}}
                    })
                continue

            # Несколько значений через запятую -> terms
            if "," in value:
                must_filters.append({
                    "terms": {field: value.split(",")}
                })
            else:
                # Обычный term-фильтр
                must_filters.append({
                    "term": {field: value}
                })

        query = {"query": {"bool": {"must": must_filters}}} if must_filters else {"query": {"match_all": {}}}

        res = es.search(index=INDEX_PREFIX, body=query, size=100)

        return Response([hit["_source"] for hit in res["hits"]["hits"]])
    
