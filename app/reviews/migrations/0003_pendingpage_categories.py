from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0002_pendingrevision_superset_data"),
    ]

    operations = [
        migrations.AddField(
            model_name="pendingpage",
            name="categories",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
