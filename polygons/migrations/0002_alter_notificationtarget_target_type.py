# Generated manually for WebSocket notification system

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("polygons", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notificationtarget",
            name="target_type",
            field=models.CharField(
                choices=[("api_key", "API ключ"), ("device", "Устройство")],
                max_length=20,
                verbose_name="Тип цели",
            ),
        ),
    ]
