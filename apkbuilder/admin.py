from django.contrib import admin
from .models import APKBuild


@admin.register(APKBuild)
class APKBuildAdmin(admin.ModelAdmin):
    list_display = ['app_name', 'user', 'status', 'created_at', 'completed_at']
    list_filter = ['status', 'created_at']
    search_fields = ['app_name', 'package_name']
    readonly_fields = ['id', 'created_at', 'completed_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('id', 'user', 'api_key', 'status')
        }),
        ('Информация о приложении', {
            'fields': ('app_name', 'package_name', 'version_code', 'version_name')
        }),
        ('Файлы', {
            'fields': ('source_file', 'output_file')
        }),
        ('Временные метки', {
            'fields': ('created_at', 'completed_at')
        }),
    )