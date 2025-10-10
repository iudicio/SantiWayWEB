from rest_framework import serializers
from .models import Polygon, PolygonAction, NotificationTarget, AnomalyDetection, Notification
from .utils import validate_polygon_geometry, calculate_polygon_area


class PolygonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Polygon
        fields = [
            "id",
            "name",
            "description",
            "geometry",
            "area",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "area", "created_at", "updated_at"]

    def validate_geometry(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("geometry must be GeoJSON object")
        if not validate_polygon_geometry(value):
            raise serializers.ValidationError("invalid polygon geometry")
        return value

    def create(self, validated_data):
        geometry = validated_data.get("geometry")
        coords = geometry.get("coordinates", [[]])[0]
        validated_data["area"] = calculate_polygon_area(coords)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        geometry = validated_data.get("geometry", instance.geometry)
        coords = geometry.get("coordinates", [[]])[0]
        instance.area = calculate_polygon_area(coords)
        instance.name = validated_data.get("name", instance.name)
        instance.description = validated_data.get("description", instance.description)
        instance.geometry = geometry
        instance.is_active = validated_data.get("is_active", instance.is_active)
        instance.save()
        return instance


class PolygonActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolygonAction
        fields = [
            "id",
            "polygon",
            "action_type",
            "parameters",
            "status",
            "task_id",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "task_id",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
        ]


class NotificationTargetSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTarget
        fields = [
            "id",
            "target_type",
            "target_value",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_target_value(self):
        """Валидация значения цели в зависимости от типа"""
        target_type = self.initial_data.get('target_type')
        target_value = self.initial_data.get('target_value')
        
        if target_type not in ['api_key', 'device']:
            raise serializers.ValidationError(f"Недопустимый тип цели: {target_type}. Доступны: api_key, device")
        
        if not target_value or not isinstance(target_value, str):
            raise serializers.ValidationError("target_value должен быть непустой строкой")
        
        return target_value


class AnomalyDetectionSerializer(serializers.ModelSerializer):
    polygon_name = serializers.CharField(source='polygon_action.polygon.name', read_only=True)
    
    class Meta:
        model = AnomalyDetection
        fields = [
            "id",
            "polygon_action",
            "polygon_name",
            "anomaly_type",
            "severity",
            "device_id",
            "device_data",
            "description",
            "metadata",
            "is_resolved",
            "resolved_at",
            "resolved_by",
            "detected_at",
        ]
        read_only_fields = [
            "id",
            "polygon_name",
            "resolved_at",
            "detected_at",
        ]


class NotificationSerializer(serializers.ModelSerializer):
    anomaly_details = AnomalyDetectionSerializer(source='anomaly', read_only=True)
    target_details = NotificationTargetSerializer(source='target', read_only=True)
    
    class Meta:
        model = Notification
        fields = [
            "id",
            "anomaly",
            "anomaly_details",
            "target",
            "target_details",
            "title",
            "message",
            "status",
            "delivery_metadata",
            "created_at",
            "sent_at",
            "delivered_at",
            "read_at",
            "retry_count",
            "max_retries",
        ]
        read_only_fields = [
            "id",
            "anomaly_details",
            "target_details",
            "created_at",
            "sent_at",
            "delivered_at",
            "read_at",
            "retry_count",
        ]


class PolygonActionWithTargetsSerializer(serializers.ModelSerializer):
    """Расширенный сериализатор для PolygonAction с целями уведомлений"""
    notification_targets = NotificationTargetSerializer(many=True, required=False)
    
    class Meta:
        model = PolygonAction
        fields = [
            "id",
            "polygon",
            "action_type",
            "parameters",
            "status",
            "task_id",
            "notification_targets",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "task_id",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
        ]
    
    def create(self, validated_data):
        notification_targets_data = validated_data.pop('notification_targets', [])
        polygon_action = super().create(validated_data)
        
        for target_data in notification_targets_data:
            NotificationTarget.objects.create(
                polygon_action=polygon_action,
                **target_data
            )
        
        return polygon_action
