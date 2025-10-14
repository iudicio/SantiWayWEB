from celery import Celery
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView
from elasticsearch import Elasticsearch
from elasticsearch import NotFoundError
from django.conf import settings
from .serializers import DeviceSerializer, WaySerializer
from .auth import APIKeyAuthentication
from .permissions import HasAPIKey
from celery import Celery
from os import getenv
import uuid


ES_HOST = getattr(settings, "ELASTICSEARCH_DSN", getenv("ES_URL", None))
ES_USER = getenv("ES_USER", None)
ES_PASSWORD = getenv("ES_PASSWORD", None)

BROKER_URL = getenv('CELERY_BROKER_URL', "amqp://celery:celerypassword@rabbitmq:5672//")
BACKEND = getenv("CELERY_RESULT_BACKEND", "redis://:strongpassword@redis:6379/0")

celery_client = Celery('producer', broker=BROKER_URL, backend=BACKEND)

print("PRODUCER broker:", celery_client.connection().as_uri())
print("PRODUCER backend:", celery_client.backend.as_uri())

es = None
if ES_HOST:
    try:
        es = Elasticsearch(hosts=ES_HOST)
    except Exception:
        es = None


class DeviceViewSet(viewsets.ViewSet):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasAPIKey]
    serializer_class = DeviceSerializer
    lookup_field = "device_id"


    def list(self, request, *args, **kwargs):
        global es
        if es is None and ES_HOST:
            try:
                es = Elasticsearch(hosts=ES_HOST)
            except Exception as e:
                return Response({"error": f"Elasticsearch init failed: {e}"}, status=status.HTTP_502_BAD_GATEWAY)
        must_filters = []
        
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

        query = {"query": {"bool": {"filter": must_filters}}} if must_filters else {"query": {"match_all": {}}}
        try:
            if es is None:
                return Response({"error": "Elasticsearch is not configured"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            res = es.search(index="way", body=query, size=100)
        except NotFoundError:
            return Response([], status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": f"Elasticsearch query failed: {e}"}, status=status.HTTP_502_BAD_GATEWAY)

        return Response([hit["_source"] for hit in res["hits"]["hits"]])

    def create(self, request, *args, **kwargs):
        global celery_client
        data = request.data
        celery_client.send_task('vendor', args=[data], queue='vendor_queue')
        return Response({'status': 'queued'}, status=status.HTTP_202_ACCEPTED)
    
class WayAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        global celery_client
        serializer = WaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not data.get("devices"):
            result = celery_client.send_task('devices', args=[data], queue="info_queue")
        else:
            result = celery_client.send_task('folders', args=[data], queue="info_queue")
        print("Ждем ответ")
        response = result.get(timeout=5)
        print("Ответ: ", response)
        return Response(response)
        
