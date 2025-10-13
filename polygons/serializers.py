from rest_framework import serializers
from .models import Polygon, PolygonAction
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
