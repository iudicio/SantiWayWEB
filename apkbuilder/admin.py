from django.contrib import admin
from .models import APKBuild


@admin.register(APKBuild)
class APKBuildAdmin(admin.ModelAdmin):
    list_display = ["user", "status", "created_at", "completed_at"]
    list_filter = ["status", "created_at"]
    readonly_fields = ["id", "created_at", "completed_at"]

    fieldsets = (
        ("Основная информация", {"fields": ("id", "user", "api_key", "status")}),
        ("Временные метки", {"fields": ("created_at", "completed_at")}),
    )
