from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from pages.seo import noindex

from . import views
from .forms import StudentPasswordResetForm

app_name = "accounts"

# Django's own password views render through `accounts/_auth_shell.html`, which
# takes its heading and page title from `seo`. Supplying it here keeps those
# pages consistent with the rest of the site without subclassing each view.
urlpatterns = [
    path("login/", views.StudentLoginView.as_view(), name="login"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("logout/", views.StudentLogoutView.as_view(), name="logout"),
    path("account/confirm/sent/", views.ConfirmSentView.as_view(), name="confirm_sent"),
    path(
        "account/confirm/resend/",
        views.ResendConfirmationView.as_view(),
        name="confirm_resend",
    ),
    path(
        "account/confirm/<uidb64>/<token>/",
        views.ConfirmEmailView.as_view(),
        name="confirm_email",
    ),
    path("account/", views.AccountSettingsView.as_view(), name="settings"),
    path("account/orders/", views.OrderHistoryView.as_view(), name="orders"),
    path(
        "account/password/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/password_change.html",
            success_url=reverse_lazy("accounts:password_change_done"),
            extra_context={"seo": noindex("Change your password")},
        ),
        name="password_change",
    ),
    path(
        "account/password/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="accounts/password_change_done.html",
            extra_context={"seo": noindex("Password changed")},
        ),
        name="password_change_done",
    ),
    path(
        "password/reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            form_class=StudentPasswordResetForm,
            email_template_name="accounts/email/password_reset.txt",
            subject_template_name="accounts/email/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
            extra_context={"seo": noindex("Reset your password")},
        ),
        name="password_reset",
    ),
    path(
        "password/reset/sent/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html",
            extra_context={"seo": noindex("Check your email")},
        ),
        name="password_reset_done",
    ),
    path(
        "password/reset/<uidb64>/<token>/",
        views.StudentPasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
            extra_context={"seo": noindex("Choose a new password")},
        ),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html",
            extra_context={"seo": noindex("Your password is set")},
        ),
        name="password_reset_complete",
    ),
]
