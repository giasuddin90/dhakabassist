"""Treat every account that existed before confirmation as confirmed.

Sign-in now needs a confirmed email. Accounts made before that rule never got
a link to click, so without this they would be locked out.
"""

from django.db import migrations
from django.db.models import F


def confirm_existing(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(email_confirmed_at__isnull=True).update(
        email_confirmed_at=F("date_joined")
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_user_email_confirmed_at"),
    ]

    # Reversing is a no-op: the column is dropped by 0004's reverse anyway.
    operations = [migrations.RunPython(confirm_existing, migrations.RunPython.noop)]
