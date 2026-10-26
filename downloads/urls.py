from django.urls import path

from . import views

app_name = "downloads"

urlpatterns = [
    path("downloads/", views.DownloadListView.as_view(), name="list"),
    path("downloads/<slug:slug>/file/", views.download_file, name="file"),
    path("my-downloads/", views.MyDownloadsView.as_view(), name="mine"),
]
