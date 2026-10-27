"""Until the access flag, a price of 0 meant free. Keep those free."""

from django.db import migrations


def mark_free(apps, schema_editor):
    Download = apps.get_model("downloads", "Download")
    Download.objects.filter(price=0).update(access="free")


def mark_premium(apps, schema_editor):
    """Nothing to undo: reversing 0002 drops the column."""


class Migration(migrations.Migration):

    dependencies = [
        ("downloads", "0002_download_access"),
    ]

    operations = [
        migrations.RunPython(mark_free, mark_premium),
    ]
