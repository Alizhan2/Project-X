from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('accounts', '0006_journeyplan_search_preferences')]

    operations = [
        # Repair databases that applied 0006 before its persistent defaults were added.
        migrations.RunSQL(
            sql="ALTER TABLE accounts_journeyplan ALTER COLUMN time_mode SET DEFAULT 'departure', "
                "ALTER COLUMN wheelchair_required SET DEFAULT false",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
