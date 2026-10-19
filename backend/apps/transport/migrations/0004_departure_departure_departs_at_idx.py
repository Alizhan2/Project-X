from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction. It does not block writes, which matters on a large
    # departures table in production (see docs/release-procedure.md, "migration rules").
    atomic = False

    dependencies = [
        ("transport", "0003_departure_baseline_places_and_more"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="departure",
            index=models.Index(fields=["departs_at"], name="departure_departs_at_idx"),
        ),
    ]
