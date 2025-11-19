# Generated migration for adding Lift Wing caching fields

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reviews", "0011_add_liftwing_ml_fields"),
    ]

    operations = [
        # Update ores_fetched_at to allow null
        migrations.AlterField(
            model_name="modelscores",
            name="ores_fetched_at",
            field=models.DateTimeField(
                blank=True, help_text="When ORES scores were fetched from the API", null=True
            ),
        ),
        # Add Lift Wing cache fields
        migrations.AddField(
            model_name="modelscores",
            name="lw_revertrisk_score",
            field=models.FloatField(
                blank=True,
                help_text="Lift Wing language-agnostic revert risk probability (0.0-1.0)",
                null=True,
                validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
            ),
        ),
        migrations.AddField(
            model_name="modelscores",
            name="lw_revertrisk_language_agnostic_score",
            field=models.FloatField(
                blank=True,
                help_text="Lift Wing language-agnostic revert risk probability (0.0-1.0)",
                null=True,
                validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
            ),
        ),
        migrations.AddField(
            model_name="modelscores",
            name="lw_revertrisk_multilingual_score",
            field=models.FloatField(
                blank=True,
                help_text="Lift Wing multilingual revert risk probability (0.0-1.0)",
                null=True,
                validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
            ),
        ),
        migrations.AddField(
            model_name="modelscores",
            name="lw_damaging_score",
            field=models.FloatField(
                blank=True,
                help_text="Lift Wing damaging probability (0.0-1.0)",
                null=True,
                validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
            ),
        ),
        migrations.AddField(
            model_name="modelscores",
            name="lw_goodfaith_score",
            field=models.FloatField(
                blank=True,
                help_text="Lift Wing goodfaith probability (0.0-1.0)",
                null=True,
                validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
            ),
        ),
        migrations.AddField(
            model_name="modelscores",
            name="lw_fetched_at",
            field=models.DateTimeField(
                blank=True, help_text="When Lift Wing scores were fetched from the API", null=True
            ),
        ),
    ]
