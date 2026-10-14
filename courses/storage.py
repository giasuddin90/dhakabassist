"""Storage for paid course material.

Files land outside `MEDIA_ROOT` and the storage has no public base URL, so
there is no way to link one directly. `courses.views.protected_asset` is the
only route to the bytes, and it checks enrolment first.
"""

import os

from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.core.files.storage import FileSystemStorage


class ProtectedStorage(FileSystemStorage):
    """A filesystem storage rooted at `PROTECTED_MEDIA_ROOT`, resolved lazily.

    The location is read from settings on each access rather than captured at
    import time, so a deployment (or a test) that points the setting elsewhere
    is honoured.
    """

    @property
    def base_location(self):
        return str(settings.PROTECTED_MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None

    def url(self, name):
        raise SuspiciousOperation(
            "Protected course files have no public URL; use courses:asset."
        )


protected_storage = ProtectedStorage()
