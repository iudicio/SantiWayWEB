from django.contrib import admin
from .models import Polygon, PolygonAction


@admin.register(Polygon)
class PolygonAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "area", "is_active", "created_at"]
    list_filter = ["is_active", "created_at", "user"]
    search_fields = ["name", "description", "user__username"]
    readonly_fields = ["id", "created_at", "updated_at"]
    raw_id_fields = ["user"]


@admin.register(PolygonAction)
class PolygonActionAdmin(admin.ModelAdmin):
    list_display = ["polygon", "action_type", "status", "created_at", "started_at"]
    list_filter = ["action_type", "status", "created_at"]
    search_fields = ["polygon__name", "polygon__user__username"]
    readonly_fields = ["id", "created_at", "updated_at", "started_at", "completed_at"]
    raw_id_fields = ["polygon"]
