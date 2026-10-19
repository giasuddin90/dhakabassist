"""Request middleware for the project as a whole."""

from django.utils import translation

# Staff tools are written in English; their forms edit both languages.
STAFF_PATH_PREFIXES = ("/manage/", "/django-admin/")


def staff_language_middleware(get_response):
    """Serve the staff tools in English whatever the browser asks for.

    They sit outside the language prefix, so `LocaleMiddleware` would
    otherwise pick a language from the cookie or Accept-Language header
    and mix Bangla labels into English pages.
    """

    def middleware(request):
        if request.path_info.startswith(STAFF_PATH_PREFIXES):
            translation.activate("en")
            request.LANGUAGE_CODE = "en"
        return get_response(request)

    return middleware
