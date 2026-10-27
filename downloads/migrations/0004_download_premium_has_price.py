from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("downloads", "0003_free_downloads_by_price"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='download',
            constraint=models.CheckConstraint(condition=models.Q(('access', 'free'), ('price__gt', 0), _connector='OR'), name='download_premium_has_price', violation_error_message='A premium download needs a price above 0.'),
        ),
    ]
