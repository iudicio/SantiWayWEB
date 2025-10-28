from rest_framework import serializers
from .models import SearchQuery

class PolygonSerializer(serializers.Serializer):
    # Допускаем и упрощённый вариант: один контур points=[ [lon,lat], ... ]
    points = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField()), allow_empty=False
    )

class DeviceSearchRequestSerializer(serializers.Serializer):
    # Обязательные входы (могут быть пустыми списками — тогда не фильтруем по ним)
    api_keys   = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    devices    = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    folders    = serializers.ListField(child=serializers.CharField(), required=False, default=list)

    # Прочие фильтры
    time_from  = serializers.DateTimeField(required=False, allow_null=True)
    time_to    = serializers.DateTimeField(required=False, allow_null=True)
    device_type = serializers.CharField(required=False, allow_blank=True)
    macs       = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    name       = serializers.CharField(required=False, allow_blank=True)

    is_alarm   = serializers.BooleanField(required=False, default=None)      # тревожное
    is_ignored = serializers.BooleanField(required=False, default=None)      # игнорируемое

    # Полигоны
    polygons   = PolygonSerializer(many=True, required=False, default=list)

    # Мониторинг: список MAC, по которым нужно отдать срез внутри полигонов
    monitor_macs = serializers.ListField(child=serializers.CharField(), required=False, default=list)

    # Параметры выгрузки
    save_query = serializers.BooleanField(required=False, default=True)
    limit      = serializers.IntegerField(required=False, default=300, min_value=1, max_value=10000)

class SearchQuerySerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchQuery
        fields = ["id", "created_at", "paid", "export_status", "export_file", "params", "results", "monitored_macs"]
        read_only_fields = ["id", "created_at", "results", "export_status", "export_file"]
