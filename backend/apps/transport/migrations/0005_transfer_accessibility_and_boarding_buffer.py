from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("transport", "0004_departure_departure_departs_at_idx")]

    operations = [
        migrations.AlterField(
            model_name="transferlink", name="minutes",
            field=models.PositiveSmallIntegerField(help_text="Walking time between stops"),
        ),
        migrations.AddField(
            model_name="transferlink", name="boarding_buffer_minutes",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="transferlink", name="step_free",
            field=models.BooleanField(null=True, blank=True, help_text="Unknown paths cannot satisfy strict accessibility"),
        ),
    ]
