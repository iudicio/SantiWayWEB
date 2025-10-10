from django.apps import AppConfig


class PolygonsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'polygons'
    
    def ready(self):
        """Импортируем сигналы при запуске приложения"""
        import polygons.signals  # noqa