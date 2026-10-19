"""Helpers shared by the apps' tests."""

from django.conf import settings
from django.utils import translation


# One hook is the whole of a test mixin.
class EnglishPagesMixin:  # pylint: disable=too-few-public-methods
    """Run a test case against the English pages.

    `reverse()` then gives /en/ addresses, so tests that read the English
    copy keep working while the unprefixed (Bangla) pages are the default.
    Set per class rather than in `setUp`, which test cases override without
    calling `super()`; the primary language is restored afterwards, so the
    choice never leaks into the next test case.
    """

    @classmethod
    def setUpClass(cls):  # pylint: disable=invalid-name  # unittest's hook name
        translation.activate("en")
        cls.addClassCleanup(translation.activate, settings.LANGUAGE_CODE)
        super().setUpClass()
