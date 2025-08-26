from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, APIKey, Device, SearchQuery


class DeviceInline(admin.TabularInline):
    model = Device
    extra = 1


class APIKeyAdmin(admin.ModelAdmin):
    list_display = ('key', 'created_at')
    search_fields = ('key',)
    inlines = [DeviceInline]


class SearchQueryAdmin(admin.ModelAdmin):
    list_display = ('query_text', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('query_text',)


class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ('username', 'email', 'registration_date', 'last_login_date')
    list_filter = ('registration_date', 'last_login_date')
    search_fields = ('username', 'email')
    ordering = ('-registration_date',)

    fieldsets = BaseUserAdmin.fieldsets + (
        (None, {
            'fields': ('registration_date', 'api_keys', 'last_login_date', 'search_queries')
        }),
    )


# Регистрируем все модели
admin.site.register(User, UserAdmin)
admin.site.register(APIKey, APIKeyAdmin)
admin.site.register(Device)
admin.site.register(SearchQuery, SearchQueryAdmin)