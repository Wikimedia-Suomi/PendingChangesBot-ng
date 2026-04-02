# Generated for PendingChangesBot-ng

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0010_modelscores"),
    ]

    operations = [
        migrations.AddField(
            model_name="wikiconfiguration",
            name="ml_model_type",
            field=models.CharField(
                max_length=50,
                default='revertrisk',
                choices=[
                    ('revertrisk', 'Revert Risk (language-agnostic)'),
                    ('damaging', 'Damaging Edit Detection'),
                    ('goodfaith', 'Good Faith Prediction'),
                    ('articlequality', 'Article Quality Assessment'),
                    ('articletopic', 'Article Topic Classification'),
                ],
                help_text="Which Wikimedia Lift Wing ML model to use for this wiki"
            ),
        ),
        migrations.AddField(
            model_name="wikiconfiguration",
            name="ml_model_threshold",
            field=models.FloatField(
                default=0.0,
                validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
                help_text=(
                    "Threshold for Lift Wing ML model score (0.0-1.0). "
                    "Edits with a score above this threshold will not be auto-approved. "
                    "Set to 0.0 to disable Lift Wing ML model checking."
                ),
            ),
        ),
    ]
