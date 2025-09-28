from rest_framework import serializers
from .models import APKBuild


class APKBuildCreateSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, source='api-key')

    class Meta:
        model = APKBuild
        fields = [
            'api_key',
            'app_name',
            'package_name',
            'version_code',
            'version_name',
            'source_file'
        ]
        extra_kwargs = {
            'source_file': {'required': True},
            'api_key': {'required': True}
        }

    def validate(self, attrs):
        attrs.pop('api-key', None)
        return attrs


class APKBuildStatusSerializer(serializers.ModelSerializer):
    build_duration = serializers.ReadOnlyField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = APKBuild
        fields = [
            'id',
            'status',
            'status_display',
            'created_at',
            'completed_at',
            'build_duration',
            'app_name',
            'package_name',
            'version_code',
            'version_name',
            'api_key'
        ]
        read_only_fields = fields