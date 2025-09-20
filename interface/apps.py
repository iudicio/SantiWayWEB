from django.apps import AppConfig


class InterfaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "interface"
    verbose_name = "Web Interface"

    def ready(self):
        """Хук инициализации приложения."""
        pass