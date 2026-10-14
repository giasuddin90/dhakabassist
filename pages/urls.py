from django.urls import path

from . import views

app_name = "pages"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("about/", views.AboutView.as_view(), name="about"),
    path("faq/", views.FaqView.as_view(), name="faq"),
    path("legal/<slug:slug>/", views.LegalPageView.as_view(), name="legal"),
]
