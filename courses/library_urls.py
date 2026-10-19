"""The media library's file URL, kept outside the language prefix.

Administrators paste these links into lesson notes in either language, and
access checks find them by matching the path inside the notes, so the path
must be the same whatever language the page is in.
"""

from django.urls import path

from . import views

app_name = "library"

urlpatterns = [
    path("library/<str:key>/<str:name>", views.library_file, name="file"),
]
