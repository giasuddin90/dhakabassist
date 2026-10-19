from django.urls import path

from . import views

app_name = "courses"

urlpatterns = [
    path("courses/", views.CourseListView.as_view(), name="list"),
    path("courses/<slug:slug>/", views.CourseDetailView.as_view(), name="detail"),
    path("authors/<slug:slug>/photo/", views.author_photo, name="author_photo"),
    path("my-courses/", views.DashboardView.as_view(), name="dashboard"),
    path(
        "learn/<slug:slug>/<slug:module_slug>/",
        views.LessonView.as_view(),
        name="lesson",
    ),
    path(
        "learn/<slug:slug>/<slug:module_slug>/quiz/",
        views.QuizView.as_view(),
        name="quiz",
    ),
    path(
        "learn/<slug:slug>/<slug:module_slug>/quiz/answer/",
        views.quiz_answer,
        name="quiz_answer",
    ),
    path(
        "learn/<slug:slug>/<slug:module_slug>/quiz/next/",
        views.quiz_advance,
        name="quiz_advance",
    ),
    path(
        "learn/<slug:slug>/<slug:module_slug>/quiz/restart/",
        views.quiz_restart,
        name="quiz_restart",
    ),
    path("module/<int:pk>/position/", views.save_video_position, name="video_position"),
    path("module/<int:pk>/video/", views.protected_video, name="video"),
    path("asset/<int:pk>/", views.protected_asset, name="asset"),
    path("library/<str:key>/<str:name>", views.library_file, name="library_file"),
]
