from rest_framework import serializers
from django.utils import timezone

class DeviceSerializer(serializers.ModelSerializer):
    mac = serializers.CharField(max_length=17)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    rssi = serializers.IntegerField()
    network_type = serializers.CharField(max_length=8)
    ignore_status = serializers.BooleanField(default=False)
    alert_status = serializers.BooleanField(default=False)
    user_api = serializers.CharField(max_length=100, allow_blank=True)
    user_mac = serializers.CharField(max_length=17, allow_blank=True)
    time = serializers.DateTimeField(default_timezone=timezone.now)
    folder_name = serializers.CharField(max_length=100, allow_blank=True)
    folder_sys_name = serializers.CharField(max_length=100, allow_blank=True)