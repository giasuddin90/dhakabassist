"""Existing videos, trailers and asset files become the English version.

Both languages fall back to them until a Bangla version is added, so
nothing a student sees changes. The next migration adds the Bangla columns.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("courses", "0011_bangla_content_columns")]

    operations = [
        migrations.RenameField("course", "trailer_url", "trailer_url_en"),
        migrations.RenameField("course", "trailer_duration", "trailer_duration_en"),
        migrations.RenameField("module", "video_uid", "video_uid_en"),
        migrations.RenameField("module", "video_duration_seconds", "video_duration_seconds_en"),
        migrations.RenameField("module", "video_has_subtitles", "video_has_subtitles_en"),
        migrations.RenameField("mediaasset", "file", "file_en"),
        migrations.RenameField("mediaasset", "duration_seconds", "duration_seconds_en"),
    ]
