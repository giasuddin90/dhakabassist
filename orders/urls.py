from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("enroll/<slug:slug>/", views.checkout, name="checkout"),
    path("downloads/<slug:slug>/buy/", views.download_checkout, name="download_checkout"),
    path("payment/<str:reference>/", views.sandbox, name="sandbox"),
    path(
        "payment/<str:reference>/complete/",
        views.sandbox_complete,
        name="sandbox_complete",
    ),
    path("payment/return/<str:outcome>/", views.callback, name="callback"),
    path("payment/ipn/", views.ipn, name="ipn"),
    path("receipt/<str:reference>/", views.receipt, name="receipt"),
]
