# Generated migration for updating ML model choices

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reviews", "0012_add_liftwing_cache_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="wikiconfiguration",
            name="ml_model_type",
            field=models.CharField(
                choices=[
                    ("revertrisk_language_agnostic", "Revert Risk (language-agnostic, 250+ languages)"),
                    ("revertrisk_multilingual", "Revert Risk (multilingual, 47 languages, higher accuracy)"),
                    ("damaging", "Damaging Edit Detection (47 languages)"),
                    ("goodfaith", "Good Faith Prediction (47 languages)"),
                    ("articlequality", "Article Quality Assessment (wiki-specific)"),
                    ("articletopic", "Article Topic Classification (wiki-specific)"),
                ],
                default="revertrisk_language_agnostic",
                help_text="Which Wikimedia Lift Wing ML model to use for this wiki. Check compatibility with your wiki language!",
                max_length=50,
            ),
        ),
    ]
