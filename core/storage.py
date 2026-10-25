"""Static file storage for development and tests."""

import os

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage


class VersionedStaticFilesStorage(StaticFilesStorage):
    """Add the file's modification time to every static URL.

    Production gets hashed filenames from `collectstatic`. Without them a
    browser keeps showing the old CSS or JS after an edit, so the URL changes
    whenever the file does instead (`site.css?v=1761465600`).
    """

    def url(self, name):
        url = super().url(name)
        path = finders.find(name) if name else None
        if not path:
            return url
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}v={int(os.path.getmtime(path))}"
