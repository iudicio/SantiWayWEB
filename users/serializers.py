from rest_framework import serializers

from .models import APIKey, Device


class DeviceAPIKeySerializer(serializers.ModelSerializer):
    api_key = serializers.UUIDField(read_only=True, source="api_key.key")

    class Meta:
        model = Device
        fields = ["id", "name", "api_key"]
