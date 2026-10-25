"""Static URLs outside production carry the file's modification time."""

import os

from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.test import SimpleTestCase


class VersionedStaticUrlTests(SimpleTestCase):
    """`{% static %}` in development and tests."""

    def test_url_carries_modification_time(self):
        """An edited file gets a new URL, so the browser fetches it again."""
        mtime = int(os.path.getmtime(finders.find("css/site.css")))
        self.assertEqual(static("css/site.css"), f"/static/css/site.css?v={mtime}")

    def test_missing_file_keeps_plain_url(self):
        """A path no finder knows is left alone rather than raising."""
        self.assertEqual(static("css/missing.css"), "/static/css/missing.css")
