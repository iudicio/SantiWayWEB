from rest_framework import viewsets, status
from rest_framework.response import Response
from elasticsearch import Elasticsearch
from .serializers import DeviceSerializer
from os import getenv
import uuid

ES_HOST = getenv("ES_HOST", None)
ES_USER = getenv("ES_USER", None)
ES_PASSWORD = getenv("ES_PASSWORD", None)

es = Elasticsearch(
            hosts = "http://localhost:9200/" # ES_HOST
        )


class DeviceViewSet(viewsets.ViewSet):
    serializer_class = DeviceSerializer
    lookup_field = "device_id"


    def list(self, request, *args, **kwargs):
        must_filters = []
        global es
        for field, value in request.query_params.items():
            # Диапазоны (например: ?timestamp__gte=2025-01-01T00:00:00)
            if "__" in field:
                field_name, op = field.split("__", 1)
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
        print(query)
        res = es.search(index="way", body=query, size=100)

        return Response([hit["_source"] for hit in res["hits"]["hits"]])
    
    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        global es
        doc = serializer.validated_data

        # уникальный id: device_id + timestamp, иначе uuid
        if "detected_at" in doc and doc["detected_at"]:
            doc_id = f"{doc['device_id']}_{int(doc['detected_at'].timestamp())}"
        else:
            doc_id = str(uuid.uuid4())

        # всегда пишем в alias "way"
        es.index(index="way", id=doc_id, document=doc)

        return Response({"id": doc_id, **doc}, status=status.HTTP_201_CREATED)

        
    
