from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "pages"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("contact/", views.ContactView.as_view(), name="contact"),
    # The About page is hidden; old links land on the contact form.
    path("about/", RedirectView.as_view(pattern_name="pages:contact", permanent=True)),
    path("faq/", views.FaqView.as_view(), name="faq"),
    path("legal/<slug:slug>/", views.LegalPageView.as_view(), name="legal"),
]
