from django.utils import timezone

from rest_framework import serializers


# Сериализатор для устройств
class DeviceSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=17)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    signal_strength = serializers.IntegerField()
    network_type = serializers.CharField(max_length=8)
    is_ignored = serializers.BooleanField(default=False)
    is_alert = serializers.BooleanField(default=False)
    user_api = serializers.CharField(max_length=100, allow_blank=True)
    user_phone_mac = serializers.CharField(max_length=17, allow_blank=True)
    detected_at = serializers.DateTimeField(default=timezone.now)
    folder_name = serializers.CharField(max_length=100, allow_blank=True)
    system_folder_name = serializers.CharField(max_length=100, allow_blank=True)


class WaySerializer(serializers.Serializer):
    api_keys = serializers.ListField(
        child=serializers.CharField(), required=True, allow_empty=False
    )
    devices = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=False
    )
