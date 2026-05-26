from django.db import connection, migrations


def vacuum_sqlite(apps, schema_editor):
    if connection.vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute("VACUUM;")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("crm", "0007_drop_legacy_lead_fields"),
    ]

    operations = [
        migrations.RunPython(vacuum_sqlite, migrations.RunPython.noop),
    ]
