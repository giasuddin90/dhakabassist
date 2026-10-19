"""Existing content is English: keep it, under its `_en` column.

Bangla columns, and the rules that need one language or the other, are
added by the next migration. Renaming keeps the data and reverses cleanly.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("pages", "0001_initial")]

    operations = [
        migrations.RenameField("faq", "question", "question_en"),
        migrations.RenameField("faq", "answer", "answer_en"),
        migrations.RenameField("legalpage", "title", "title_en"),
        migrations.RenameField("legalpage", "body_markdown", "body_markdown_en"),
        migrations.RenameField("legalpage", "meta_description", "meta_description_en"),
    ]
