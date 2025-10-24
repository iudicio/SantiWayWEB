from django.contrib import admin
from .models import Polygon, PolygonAction, NotificationTarget, AnomalyDetection, Notification


@admin.register(Polygon)
class PolygonAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "area", "is_active", "created_at"]
    list_filter = ["is_active", "created_at", "user"]
    search_fields = ["name", "description", "user__username"]
    readonly_fields = ["id", "created_at", "updated_at"]
    raw_id_fields = ["user"]


@admin.register(PolygonAction)
class PolygonActionAdmin(admin.ModelAdmin):
    list_display = ['polygon', 'action_type', 'status', 'created_at', 'started_at']
    list_filter = ['action_type', 'status', 'created_at']
    search_fields = ['polygon__name', 'polygon__user__username']
    readonly_fields = ['id', 'created_at', 'updated_at', 'started_at', 'completed_at']
    raw_id_fields = ['polygon']


@admin.register(NotificationTarget)
class NotificationTargetAdmin(admin.ModelAdmin):
    list_display = ['polygon_action', 'target_type', 'target_value', 'is_active', 'created_at']
    list_filter = ['target_type', 'is_active', 'created_at']
    search_fields = ['target_value', 'polygon_action__polygon__name']
    readonly_fields = ['id', 'created_at']
    raw_id_fields = ['polygon_action']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('polygon_action__polygon')


@admin.register(AnomalyDetection)
class AnomalyDetectionAdmin(admin.ModelAdmin):
    list_display = ['polygon_action', 'anomaly_type', 'severity', 'device_id', 'is_resolved', 'detected_at']
    list_filter = ['anomaly_type', 'severity', 'is_resolved', 'detected_at']
    search_fields = ['device_id', 'description', 'polygon_action__polygon__name']
    readonly_fields = ['id', 'detected_at', 'resolved_at']
    raw_id_fields = ['polygon_action', 'resolved_by']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('id', 'polygon_action', 'anomaly_type', 'severity', 'device_id')
        }),
        ('Детали аномалии', {
            'fields': ('description', 'device_data', 'metadata')
        }),
        ('Временные метки', {
            'fields': ('detected_at', 'is_resolved', 'resolved_at', 'resolved_by')
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('polygon_action__polygon', 'resolved_by')
    
    actions = ['mark_as_resolved']
    
    def mark_as_resolved(self, request, queryset):
        updated = 0
        for anomaly in queryset:
            if not anomaly.is_resolved:
                anomaly.resolve(user=request.user)
                updated += 1
        self.message_user(request, f'Отмечено как решенные: {updated} аномалий')
    mark_as_resolved.short_description = "Отметить выбранные аномалии как решенные"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'target', 'status', 'anomaly_type_display', 'created_at', 'sent_at']
    list_filter = ['status', 'target__target_type', 'anomaly__severity', 'created_at']
    search_fields = ['title', 'message', 'target__target_value', 'anomaly__device_id']
    readonly_fields = ['id', 'created_at', 'sent_at', 'delivered_at', 'read_at']
    raw_id_fields = ['anomaly', 'target']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('id', 'anomaly', 'target', 'title', 'message')
        }),
        ('Статус доставки', {
            'fields': ('status', 'delivery_metadata', 'retry_count', 'max_retries')
        }),
        ('Временные метки', {
            'fields': ('created_at', 'sent_at', 'delivered_at', 'read_at')
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('anomaly__polygon_action__polygon', 'target')
    
    def anomaly_type_display(self, obj):
        return obj.anomaly.get_anomaly_type_display()
    anomaly_type_display.short_description = 'Тип аномалии'
    
    actions = ['mark_as_read', 'retry_failed']
    
    def mark_as_read(self, request, queryset):
        updated = queryset.filter(status__in=['pending', 'sent', 'delivered']).count()
        for notification in queryset.filter(status__in=['pending', 'sent', 'delivered']):
            notification.mark_as_read()
        self.message_user(request, f'Отмечено как прочитанные: {updated} уведомлений')
    mark_as_read.short_description = "Отметить выбранные уведомления как прочитанные"
    
    def retry_failed(self, request, queryset):
        retried = 0
        for notification in queryset.filter(status='failed'):
            if notification.can_retry():
                notification.status = 'pending'
                notification.save()
                retried += 1
        self.message_user(request, f'Поставлено на повторную отправку: {retried} уведомлений')
    retry_failed.short_description = "Повторить отправку неудачных уведомлений"
