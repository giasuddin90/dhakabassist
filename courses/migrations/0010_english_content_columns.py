"""Existing content is English: keep it, under its `_en` column.

Bangla columns, and the rules that need one language or the other, are
added by the next migration. Renaming keeps the data and reverses cleanly.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("courses", "0009_module_order_by_number")]

    operations = [
        migrations.RenameField("author", "name", "name_en"),
        migrations.RenameField("author", "bio", "bio_en"),
        migrations.RenameField("course", "title", "title_en"),
        migrations.RenameField("course", "subtitle", "subtitle_en"),
        migrations.RenameField("course", "summary", "summary_en"),
        migrations.RenameField("course", "description", "description_en"),
        migrations.RenameField("course", "level", "level_en"),
        migrations.RenameField("course", "trailer_label", "trailer_label_en"),
        migrations.RenameField("course", "meta_title", "meta_title_en"),
        migrations.RenameField("course", "meta_description", "meta_description_en"),
        migrations.RenameField("module", "title", "title_en"),
        migrations.RenameField("module", "summary", "summary_en"),
        migrations.RenameField("module", "notes_markdown", "notes_markdown_en"),
        migrations.RenameField("lesson", "title", "title_en"),
        migrations.RenameField("mediaasset", "title", "title_en"),
        migrations.RenameField("mediaasset", "alt_text", "alt_text_en"),
        migrations.RenameField("libraryfile", "title", "title_en"),
        migrations.RenameField("quiz", "title", "title_en"),
        migrations.RenameField("question", "text", "text_en"),
        migrations.RenameField("question", "explanation", "explanation_en"),
        migrations.RenameField("choice", "text", "text_en"),
    ]
